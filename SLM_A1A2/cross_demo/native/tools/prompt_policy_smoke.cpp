#include "writing_prompt_policy.h"
#include <cstdio>

int main() {
    std::string a="<|im_start|>assistant\n<think>";
    if(!close_prefilled_thinking(a,true) || a!="<|im_start|>assistant\n<think></think>\n") return 1;
    std::string b="assistant\n<think>\n ";
    if(!close_prefilled_thinking(b,true) || b!="assistant\n<think></think>\n\n ") return 2;
    std::string c="assistant\n<think>";const auto original=c;
    if(close_prefilled_thinking(c,false) || c!=original) return 3;
    std::string d="user <think> text\nassistant\n";const auto unchanged=d;
    if(close_prefilled_thinking(d,true) || d!=unchanged) return 4;
    std::string e="assistant\n<think></think>\n";const auto closed=e;
    if(close_prefilled_thinking(e,true) || e!=closed) return 5;
    std::string f;
    if(close_prefilled_thinking(f,true) || !f.empty()) return 6;
    std::puts("PASS 6/6 interactive thinking-prefill policy cases");
}
