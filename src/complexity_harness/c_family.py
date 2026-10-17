"""Common platform declaration syntax, with byte/line-preserving normalization.

This does not expand macros or remove statements, conditions or macro bodies.
Unrecognized declaration DSLs and remaining grammar errors stay unmeasured.
"""
import re


def declaration_syntax(data):
    def spaces(match):
        return re.sub(rb"[^\r\n]", b" ", match.group())

    # Windows calling-convention modifiers decorate function declarations.
    data = re.sub(rb"\b(?:APIENTRY|CALLBACK|WINAPI|NTAPI|__cdecl|__stdcall|__fastcall|__vectorcall|_In_|_In_opt_|_Out_|_Out_opt_|_Inout_|_Inout_opt_)\b", spaces, data)
    # GLib type/registration macros contain declarations, not source statements.
    data = re.sub(rb"(?m)^[ \t]*G_(?:DECLARE_FINAL_TYPE|DECLARE_DERIVABLE_TYPE|DECLARE_INTERFACE|DEFINE_TYPE|DEFINE_TYPE_WITH_PRIVATE|DEFINE_INTERFACE)\([A-Za-z0-9_, \t\r\n:]+\)[ \t]*;?", spaces, data)
    # GLib automatic-cleanup type constructors. Keep the actual type token and
    # every byte after the type; runtime calls named similarly cannot match.
    pattern = rb"(?m)^(?P<prefix>[ \t]*(?:(?:const|static)[ \t]+)?)(?P<macro>g_auto(?:ptr|free)?)[ \t]*\([ \t]*(?P<type>[A-Za-z_][A-Za-z_0-9:]*)[ \t]*\)(?=[ \t]+[A-Za-z_][A-Za-z_0-9]*[ \t]*(?:=|;))"
    def type_token(match):
        replacement = bytearray(spaces(match))
        start = match.start("type") - match.start()
        replacement[start:start+len(match["type"])] = match["type"]
        return bytes(replacement)
    return re.sub(pattern, type_token, data)
