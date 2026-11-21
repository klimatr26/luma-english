#pragma once

// Interactive product envelope, not a gold answer or a grammar of English.
constexpr const char * writing_json_grammar = R"GBNF(
root ::= "{" ws "\"is_correct\"" ws ":" ws ("true" | "false") ws "," ws "\"corrected_text\"" ws ":" ws string ws "," ws "\"errors\"" ws ":" ws errors ws "," ws "\"feedback\"" ws ":" ws string ws "}" ws
errors ::= "[" ws (error (ws "," ws error)*)? ws "]"
error ::= "{" ws "\"original\"" ws ":" ws string ws "," ws "\"correction\"" ws ":" ws string ws "," ws "\"type\"" ws ":" ws string ws "," ws "\"explanation\"" ws ":" ws string ws "}"
string ::= "\"" ([^"\\\x00-\x1f] | "\\" (["\\/bfnrt] | "u" [0-9a-fA-F]{4}))* "\""
ws ::= [ \t\n\r]*
)GBNF";
