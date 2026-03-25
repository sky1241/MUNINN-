"""
B-SCAN-11: Dynamic Import Detector — Tests
============================================
Validates detection of eval, exec, importlib, require(variable),
reflection, DI containers across Python, JS, Go, Java, PHP, Ruby.
"""
import pytest
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine.core.scanner.dynamic_detector import (
    DynamicImport,
    ScanResult,
    scan_content,
    scan_file,
    scan_directory,
    _detect_language,
)


# ---------------------------------------------------------------------------
# Real code samples per language
# ---------------------------------------------------------------------------

PYTHON_SAMPLE = """\
import os
import json

# Normal imports
from collections import defaultdict

# Dynamic patterns
result = eval(user_input)
exec(compile(code, '<string>', 'exec'))
mod = importlib.import_module(name)
mod2 = __import__(module_name)
func = getattr(obj, method_name)(args)

# This is a comment with eval() in it
# exec("harmless")
"""

JS_SAMPLE = """\
const fs = require('fs');  // normal require — NOT dynamic
const path = require("path");

// Dynamic patterns
let x = eval(userCode);
let fn = new Function('a', 'return a + 1');
let mod = require(varName);
let lazy = import(dynamicPath);

// Normal static import() — should NOT match
// import('lodash');
"""

GO_SAMPLE = """\
package main

import (
    "fmt"
    "reflect"
)

func main() {
    v := reflect.ValueOf(x)
    t := reflect.TypeOf(x)
    fmt.Println(v, t)
}
"""

JAVA_SAMPLE = """\
import java.lang.reflect.Method;

public class Example {
    // Reflection
    Class<?> cls = Class.forName("com.example.Foo");
    Method m = cls.getMethod("bar");
    Object result = m.invoke(instance);
    Object obj = cls.newInstance();

    // DI container
    ServiceLoader<Plugin> loader = ServiceLoader.load(Plugin.class);

    @Autowired
    private FooService fooService;
}
"""

PHP_SAMPLE = """\
<?php
// Normal include
include 'config.php';
require_once 'bootstrap.php';

// Dynamic patterns
eval($userInput);
include($dynamicPath);
require_once($pluginDir . '/init.php');
include $variable;
?>
"""

RUBY_SAMPLE = """\
require 'json'

# Dynamic patterns
result = eval(user_string)
obj.send(:dynamic_method, arg)
klass = Object.const_get(class_name)
"""


class TestBSCAN11DynamicDetector:
    """Core detection tests."""

    # -- Python --------------------------------------------------------

    def test_python_eval(self):
        r = scan_content(PYTHON_SAMPLE, "test.py")
        types = [f.pattern_type for f in r.findings]
        assert "eval" in types

    def test_python_exec(self):
        r = scan_content(PYTHON_SAMPLE, "test.py")
        types = [f.pattern_type for f in r.findings]
        assert "exec" in types

    def test_python_importlib(self):
        r = scan_content(PYTHON_SAMPLE, "test.py")
        types = [f.pattern_type for f in r.findings]
        assert "importlib" in types

    def test_python_dunder_import(self):
        r = scan_content(PYTHON_SAMPLE, "test.py")
        importlib_findings = [f for f in r.findings if f.pattern_type == "importlib"]
        snippets = [f.snippet for f in importlib_findings]
        assert any("__import__" in s for s in snippets)

    def test_python_getattr_dispatch(self):
        r = scan_content(PYTHON_SAMPLE, "test.py")
        types = [f.pattern_type for f in r.findings]
        assert "reflection" in types

    def test_python_comments_ignored(self):
        r = scan_content(PYTHON_SAMPLE, "test.py")
        # Lines starting with # should be skipped
        for f in r.findings:
            assert not f.snippet.startswith("#"), f"Comment detected as finding: {f.snippet}"

    def test_python_line_numbers(self):
        r = scan_content(PYTHON_SAMPLE, "test.py")
        eval_f = [f for f in r.findings if f.pattern_type == "eval"][0]
        assert eval_f.line == 8  # "result = eval(user_input)" (line 8 due to leading blank)

    def test_python_language_tag(self):
        r = scan_content(PYTHON_SAMPLE, "test.py")
        for f in r.findings:
            assert f.language == "python"

    # -- JavaScript ----------------------------------------------------

    def test_js_eval(self):
        r = scan_content(JS_SAMPLE, "app.js")
        types = [f.pattern_type for f in r.findings]
        assert "eval" in types

    def test_js_new_function(self):
        r = scan_content(JS_SAMPLE, "app.js")
        eval_findings = [f for f in r.findings if f.pattern_type == "eval"]
        snippets = [f.snippet for f in eval_findings]
        assert any("new Function" in s for s in snippets)

    def test_js_dynamic_require(self):
        r = scan_content(JS_SAMPLE, "app.js")
        types = [f.pattern_type for f in r.findings]
        assert "require_dynamic" in types

    def test_js_static_require_not_flagged(self):
        r = scan_content(JS_SAMPLE, "app.js")
        for f in r.findings:
            assert "require('fs')" not in f.snippet
            assert 'require("path")' not in f.snippet

    def test_js_dynamic_import(self):
        r = scan_content(JS_SAMPLE, "app.js")
        dyn = [f for f in r.findings if f.pattern_type == "require_dynamic"]
        snippets = [f.snippet for f in dyn]
        assert any("import(" in s for s in snippets)

    # -- Go ------------------------------------------------------------

    def test_go_reflect(self):
        r = scan_content(GO_SAMPLE, "main.go")
        types = [f.pattern_type for f in r.findings]
        assert "reflection" in types

    def test_go_reflect_count(self):
        r = scan_content(GO_SAMPLE, "main.go")
        reflect_findings = [f for f in r.findings if f.pattern_type == "reflection"]
        assert len(reflect_findings) >= 2  # ValueOf + TypeOf

    # -- Java ----------------------------------------------------------

    def test_java_class_forname(self):
        r = scan_content(JAVA_SAMPLE, "Example.java")
        types = [f.pattern_type for f in r.findings]
        assert "reflection" in types

    def test_java_method_invoke(self):
        r = scan_content(JAVA_SAMPLE, "Example.java")
        refl = [f for f in r.findings if f.pattern_type == "reflection"]
        snippets = [f.snippet for f in refl]
        assert any(".invoke(" in s for s in snippets)

    def test_java_service_loader(self):
        r = scan_content(JAVA_SAMPLE, "Example.java")
        types = [f.pattern_type for f in r.findings]
        assert "di_container" in types

    def test_java_autowired(self):
        r = scan_content(JAVA_SAMPLE, "Example.java")
        di = [f for f in r.findings if f.pattern_type == "di_container"]
        snippets = [f.snippet for f in di]
        assert any("@Autowired" in s for s in snippets)

    # -- PHP -----------------------------------------------------------

    def test_php_eval(self):
        r = scan_content(PHP_SAMPLE, "index.php")
        types = [f.pattern_type for f in r.findings]
        assert "eval" in types

    def test_php_dynamic_include(self):
        r = scan_content(PHP_SAMPLE, "index.php")
        types = [f.pattern_type for f in r.findings]
        assert "require_dynamic" in types

    def test_php_static_include_not_flagged(self):
        r = scan_content(PHP_SAMPLE, "index.php")
        for f in r.findings:
            assert "config.php" not in f.snippet or f.pattern_type != "require_dynamic"

    # -- Ruby ----------------------------------------------------------

    def test_ruby_eval(self):
        r = scan_content(RUBY_SAMPLE, "app.rb")
        types = [f.pattern_type for f in r.findings]
        assert "eval" in types

    def test_ruby_send(self):
        r = scan_content(RUBY_SAMPLE, "app.rb")
        types = [f.pattern_type for f in r.findings]
        assert "reflection" in types

    def test_ruby_const_get(self):
        r = scan_content(RUBY_SAMPLE, "app.rb")
        refl = [f for f in r.findings if f.pattern_type == "reflection"]
        snippets = [f.snippet for f in refl]
        assert any("const_get" in s for s in snippets)

    # -- Cross-cutting -------------------------------------------------

    def test_unknown_language_flags_incomplete(self):
        r = scan_content("eval(x)", "unknown.xyz")
        assert r.coverage_incomplete is True

    def test_language_override(self):
        r = scan_content("eval(x)", "noext", language="python")
        assert len(r.findings) == 1
        assert r.findings[0].language == "python"
        assert r.coverage_incomplete is False

    def test_snippet_truncation(self):
        long_line = "result = eval(" + "x" * 300 + ")"
        r = scan_content(long_line, "test.py")
        assert len(r.findings) >= 1
        assert len(r.findings[0].snippet) <= 200

    def test_empty_content(self):
        r = scan_content("", "test.py")
        assert len(r.findings) == 0
        assert r.coverage_incomplete is False

    def test_file_field_populated(self):
        r = scan_content("eval(x)", "src/danger.py")
        assert r.findings[0].file == "src/danger.py"

    def test_dataclass_fields(self):
        r = scan_content("eval(x)", "t.py")
        f = r.findings[0]
        assert isinstance(f.file, str)
        assert isinstance(f.line, int)
        assert isinstance(f.pattern_type, str)
        assert isinstance(f.language, str)
        assert isinstance(f.snippet, str)


class TestBSCAN11LanguageDetection:
    """Language detection from file extensions."""

    def test_python_extensions(self):
        assert _detect_language("foo.py") == "python"
        assert _detect_language("bar.pyw") == "python"

    def test_js_extensions(self):
        assert _detect_language("app.js") == "javascript"
        assert _detect_language("mod.mjs") == "javascript"
        assert _detect_language("lib.ts") == "javascript"
        assert _detect_language("comp.tsx") == "javascript"

    def test_other_languages(self):
        assert _detect_language("main.go") == "go"
        assert _detect_language("App.java") == "java"
        assert _detect_language("index.php") == "php"
        assert _detect_language("app.rb") == "ruby"

    def test_unknown_extension(self):
        assert _detect_language("readme.txt") == ""
        assert _detect_language("") == ""


class TestBSCAN11FileScanning:
    """File and directory scanning."""

    def test_scan_file_nonexistent(self):
        r = scan_file("/nonexistent/path.py")
        assert r.coverage_incomplete is True
        assert len(r.findings) == 0

    def test_scan_file_real(self, tmp_path):
        p = tmp_path / "test.py"
        p.write_text("x = eval(input())\n", encoding="utf-8")
        r = scan_file(str(p))
        assert len(r.findings) == 1
        assert r.findings[0].pattern_type == "eval"

    def test_scan_directory(self, tmp_path):
        py_file = tmp_path / "a.py"
        py_file.write_text("exec(code)\n", encoding="utf-8")
        js_file = tmp_path / "b.js"
        js_file.write_text("eval(x)\n", encoding="utf-8")
        txt_file = tmp_path / "c.txt"
        txt_file.write_text("eval(x)\n", encoding="utf-8")  # should be skipped

        r = scan_directory(str(tmp_path))
        assert len(r.findings) == 2  # py + js, not txt
        langs = {f.language for f in r.findings}
        assert "python" in langs
        assert "javascript" in langs
