// One isolated worker per placement. UTF-8 JSON lines on stdout, native logs on stderr.
#include "writing_runtime_options.h"
#include "nlohmann/json.hpp"
#include <vulkan/vulkan_core.h>
#include <iostream>
#include <string>
#include <vector>
#if defined(_WIN32)
#define NOMINMAX
#include <windows.h>
static std::wstring wide(const std::string & s) {
    int n=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,s.data(),static_cast<int>(s.size()),nullptr,0);
    std::wstring r(n,L'\0'); MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,s.data(),static_cast<int>(s.size()),r.data(),n); return r;
}
static void * open_library(const std::string & s) {return LoadLibraryW(wide(s).c_str());}
static void * symbol(void * p,const char * s) {return reinterpret_cast<void *>(GetProcAddress(static_cast<HMODULE>(p),s));}
static void close_library(void * p) {if(p) FreeLibrary(static_cast<HMODULE>(p));}
#else
#include <dlfcn.h>
static void * open_library(const std::string & s) {return dlopen(s.c_str(),RTLD_NOW|RTLD_LOCAL);}
static void * symbol(void * p,const char * s) {return dlsym(p,s);}
static void close_library(void * p) {if(p) dlclose(p);}
#endif
using json=nlohmann::ordered_json;

static json driver() {
#if defined(_WIN32)
    void * vk=open_library("vulkan-1.dll");
#else
    void * vk=open_library("libvulkan.so");
#endif
    if(!vk) throw std::runtime_error("No Vulkan loader.");
    auto proc=reinterpret_cast<PFN_vkGetInstanceProcAddr>(symbol(vk,"vkGetInstanceProcAddr"));
    if(!proc) {close_library(vk);throw std::runtime_error("No Vulkan entry point.");}
    auto create=reinterpret_cast<PFN_vkCreateInstance>(proc(nullptr,"vkCreateInstance"));
    VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO}; app.pApplicationName="Writing calibration";app.apiVersion=VK_API_VERSION_1_2;
    VkInstanceCreateInfo info{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};info.pApplicationInfo=&app;
    VkInstance instance{};
    if(!create||create(&info,nullptr,&instance)!=VK_SUCCESS) {close_library(vk);throw std::runtime_error("No Vulkan 1.2 instance.");}
    auto enumerate=reinterpret_cast<PFN_vkEnumeratePhysicalDevices>(proc(instance,"vkEnumeratePhysicalDevices"));
    auto properties=reinterpret_cast<PFN_vkGetPhysicalDeviceProperties2>(proc(instance,"vkGetPhysicalDeviceProperties2"));
    auto destroy=reinterpret_cast<PFN_vkDestroyInstance>(proc(instance,"vkDestroyInstance"));
    json all=json::array();uint32_t count=0;
    if(enumerate&&properties&&enumerate(instance,&count,nullptr)==VK_SUCCESS&&count) {
        std::vector<VkPhysicalDevice> devices(count);
        if(enumerate(instance,&count,devices.data())==VK_SUCCESS) for(auto device:devices) {
            VkPhysicalDeviceDriverProperties d{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DRIVER_PROPERTIES};
            VkPhysicalDeviceProperties2 p{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2};p.pNext=&d;properties(device,&p);
            all.push_back({{"device",p.properties.deviceName},{"vendor",p.properties.vendorID},
                {"device_id",p.properties.deviceID},{"api",p.properties.apiVersion},{"driver_version",p.properties.driverVersion},
                {"driver_id",d.driverID},{"driver",d.driverInfo}});
        }
    }
    if(destroy) destroy(instance,nullptr);close_library(vk);
    if(all.empty()) throw std::runtime_error("No physical Vulkan device.");
    auto first=all.front();first["fingerprint"]=all.dump();first["status"]=0;return first;
}

static int run_worker(const std::string & directory) {
#if defined(_WIN32)
    void * library=open_library(directory+"/writing_llama_bridge.dll");
#else
    void * library=open_library(directory+"/libwriting_llama_bridge.so");
#endif
    if(!library) {std::cerr<<"Native bridge could not be loaded.\n";return 3;}
#define FUNCTION(name) auto name##_fn=reinterpret_cast<decltype(&name)>(symbol(library,#name)); if(!name##_fn){std::cerr<<"Missing native export: " #name "\n";return 4;}
    FUNCTION(wg_abi_version); FUNCTION(wg_runtime_options_version); FUNCTION(wg_probe_runtime);
    FUNCTION(wg_load_config); FUNCTION(wg_generate); FUNCTION(wg_unload); FUNCTION(wg_free_text);
    FUNCTION(wg_copy_backend); FUNCTION(wg_copy_device); FUNCTION(wg_copy_fallback_reason);
    FUNCTION(wg_get_last_metrics); FUNCTION(wg_get_offloaded_layers); FUNCTION(wg_get_total_layers); FUNCTION(wg_copy_adapter_id);
    if(wg_abi_version_fn()!=2||wg_runtime_options_version_fn()!=1) return 5;
    wg_engine * engine=nullptr;std::string line;
    while(std::getline(std::cin,line)) {
        json result;
        try {
            const auto request=json::parse(line);const std::string op=request.at("op");
            char error[4096]{},backend[4096]{},device[4096]{},fallback[4096]{},adapter[4096]{};
            if(op=="inspect") {
                const std::string path=request.at("model_path");char * output=nullptr;uint32_t length=0;
                const int status=wg_probe_runtime_fn(path.c_str(),request.at("context"),directory.c_str(),&output,&length,error,sizeof(error));
                result={{"status",status},{"error",error}};
                if(status==0&&output) {
                    try {result["inventory"]=json::parse(std::string(output,length));}
                    catch(...) {wg_free_text_fn(output);throw;}
                    try {result["inventory"]["DriverFingerprint"]=driver().at("fingerprint");}
                    catch(const std::exception & e) {result["inventory"]["DriverFingerprint"]=e.what();}
                }
                wg_free_text_fn(output);
            } else if(op=="load") {
                if(engine){wg_unload_fn(engine);engine=nullptr;}
                const std::string path=request.at("model_path"),id=request.value("adapter_id",std::string());
                const int status=wg_load_config_fn(path.c_str(),request.at("context"),directory.c_str(),
                    request.at("adapter_index"),id.c_str(),request.at("gpu_layers"),nullptr,&engine,error,sizeof(error));
                if(engine) {
                    wg_copy_backend_fn(engine,backend,sizeof(backend));wg_copy_device_fn(engine,device,sizeof(device));
                    wg_copy_fallback_reason_fn(engine,fallback,sizeof(fallback));wg_copy_adapter_id_fn(engine,adapter,sizeof(adapter));
                }
                result={{"status",status},{"error",error},{"backend",backend},{"device",device},{"fallback",fallback},
                    {"adapter_id",adapter},{"gpu_layers",engine?wg_get_offloaded_layers_fn(engine):0},
                    {"full_layers",engine?wg_get_total_layers_fn(engine):0}};
            } else if(op=="generate") {
                if(!engine) throw std::runtime_error("Load a model first.");
                const std::string system=request.at("system"),user=request.at("user");const auto & s=request.at("sampling");
                char * output=nullptr;uint32_t size=0;int32_t finish=-1,prompt=0,count=0,decoded=0,closed=0;
                double seconds=0,prefill=0,decode=0;
                const int status=wg_generate_fn(engine,system.c_str(),user.c_str(),request.at("seed"),s.at("max_tokens"),1,
                    s.at("temperature"),s.at("top_p"),s.at("top_k"),s.at("min_p"),s.at("repeat_penalty"),
                    s.at("presence_penalty"),s.at("frequency_penalty"),nullptr,&output,&size,&finish,&seconds,error,sizeof(error));
                wg_get_last_metrics_fn(engine,&prompt,&count,&decoded,&prefill,&decode,&closed);
                result={{"status",status},{"error",error},{"content",output?std::string(output,size):""},{"finish",finish},
                    {"seconds",seconds},{"prompt_tokens",prompt},{"output_tokens",count},{"decoded_tokens",decoded},
                    {"prompt_seconds",prefill},{"decode_seconds",decode},{"closed_thinking",closed!=0}};
                wg_free_text_fn(output);
            } else if(op=="driver") {result=driver();}
            else if(op=="exit") break;
            else throw std::runtime_error("Unknown worker operation.");
        } catch(const std::exception & e) {result={{"status",-10},{"error",e.what()}};}
        std::cout<<result.dump()<<std::endl;
    }
    if(engine)wg_unload_fn(engine);close_library(library);return 0;
}
#if defined(_WIN32)
int wmain(int argc,wchar_t ** argv) {
    if(argc!=2)return 2;
    const int n=WideCharToMultiByte(CP_UTF8,0,argv[1],-1,nullptr,0,nullptr,nullptr);
    std::string directory(n,'\0');WideCharToMultiByte(CP_UTF8,0,argv[1],-1,directory.data(),n,nullptr,nullptr);directory.pop_back();
    return run_worker(directory);
}
#else
int main(int argc,char ** argv) {return argc==2?run_worker(argv[1]):2;}
#endif
