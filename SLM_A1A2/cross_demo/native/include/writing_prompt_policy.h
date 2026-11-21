#pragma once
#include <string>

inline bool close_prefilled_thinking(std::string & prompt, bool guided_json) {
    if (!guided_json) return false;
    const std::string marker = "<think>";
    const auto end = prompt.find_last_not_of(" \t\r\n");
    if (end == std::string::npos || end + 1 < marker.size() ||
        prompt.compare(end + 1 - marker.size(), marker.size(), marker) != 0) return false;
    // Some templates ignore enable_thinking=false and literally prefill <think>.
    // Close that prefill before decoding; never remove or rewrite returned RAW.
    prompt.insert(end + 1, "</think>\n");
    return true;
}
