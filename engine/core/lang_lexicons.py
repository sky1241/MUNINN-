#!/usr/bin/env python3
"""
Language lexicons for cube reconstruction prompts.

Each lexicon constrains the LLM output by specifying:
- formatting: canonical formatting rules (indentation, braces, spacing)
- keywords: reserved words the LLM must use verbatim
- patterns: idiomatic patterns (error handling, imports, declarations)
- constraints: hard rules (no tabs/spaces mix, specific line endings)

Used by FIMReconstructor to inject language-specific constraints into prompts.
"""

LEXICONS = {
    "python": {
        "name": "Python",
        "formatting": [
            "4 spaces indentation (PEP 8), NEVER tabs",
            "no semicolons at end of lines",
            "blank line between top-level definitions",
            "two blank lines before class/function at module level",
            "snake_case for functions and variables",
            "PascalCase for classes",
            "UPPER_CASE for constants",
        ],
        "patterns": [
            "def func(args): with colon",
            "class Name: or class Name(Base):",
            "if/elif/else: with colon, no parentheses around condition",
            "for x in iterable:",
            "with open(path) as f:",
            "try/except/finally:",
            "return, yield, raise",
            "list comprehension: [x for x in items if cond]",
            "f-strings: f'{var}'",
            "import X / from X import Y",
            "self as first method parameter",
            "@decorator syntax",
            "__init__, __str__, __repr__ dunder methods",
        ],
        "error_handling": "try/except ExceptionType as e:",
        "string_quotes": "single or double, consistent within file",
        "comments": "# for inline, triple quotes for docstrings",
        "type_hints": "def func(x: int) -> str:",
    },

    "go": {
        "name": "Go",
        "formatting": [
            "gofmt canonical: tabs for indentation",
            "opening brace on SAME line (K&R style mandatory)",
            "no parentheses in if/for/switch conditions",
            "no semicolons (implicit)",
            "CamelCase for exported, camelCase for unexported",
        ],
        "patterns": [
            "func name(params) returnType {",
            "if err != nil { return err }",
            ":= for short variable declaration",
            "var name Type for explicit declaration",
            "defer func() for cleanup",
            "go func() for goroutines",
            "chan Type for channels",
            "select { case <-ch: }",
            "interface { Method() }",
            "struct { Field Type }",
            "make([]Type, len, cap)",
            "range for iteration",
            "package main / import ()",
            "func (r *Receiver) Method()",
        ],
        "error_handling": "if err != nil { return fmt.Errorf(...) }",
        "string_quotes": 'double quotes only, backtick for raw',
        "comments": "// for inline, /* */ for block",
        "imports": 'import ( "fmt" )',
    },

    "rust": {
        "name": "Rust",
        "formatting": [
            "rustfmt canonical: 4 spaces indentation",
            "opening brace on same line",
            "snake_case for functions/variables",
            "PascalCase for types/traits",
            "SCREAMING_SNAKE for constants",
            "trailing comma in multi-line",
        ],
        "patterns": [
            "fn name(param: Type) -> ReturnType {",
            "let mut var = value;",
            "let var: Type = value;",
            "match expr { Pattern => value, }",
            "if let Some(x) = option {",
            "impl Trait for Struct {",
            "struct Name { field: Type }",
            "enum Name { Variant(Type) }",
            "&self, &mut self for methods",
            "use crate::module::item;",
            "pub fn / pub struct for public",
            "Vec<T>, HashMap<K,V>, Option<T>, Result<T,E>",
            "#[derive(Debug, Clone)]",
            "lifetime annotations: <'a>",
            ".unwrap(), .expect(), ? operator",
        ],
        "error_handling": "Result<T, E> with ? operator",
        "string_quotes": 'double quotes only, r#"raw"#',
        "comments": "// inline, /// doc comments, //! module docs",
        "semicolons": "required at end of statements, NO semicolon on last expression (implicit return)",
    },

    "javascript": {
        "name": "JavaScript",
        "formatting": [
            "2 spaces indentation (common convention)",
            "semicolons optional but consistent",
            "camelCase for variables/functions",
            "PascalCase for classes/components",
            "UPPER_CASE for constants",
        ],
        "patterns": [
            "const/let (never var)",
            "arrow functions: (args) => { }",
            "async/await pattern",
            "template literals: `${var}`",
            "destructuring: const { a, b } = obj",
            "spread: ...args, ...obj",
            "import X from 'module'",
            "export default / export { name }",
            "class Name extends Base { constructor() {} }",
            "Array methods: map, filter, reduce, forEach",
            "Promise.all, Promise.resolve",
            "try/catch/finally",
            "typeof, instanceof",
            "=== strict equality",
            "?. optional chaining, ?? nullish coalescing",
        ],
        "error_handling": "try { } catch (err) { }",
        "string_quotes": "single quotes or backticks preferred",
        "comments": "// inline, /* */ block, /** */ JSDoc",
    },

    "typescript": {
        "name": "TypeScript",
        "formatting": [
            "2 spaces indentation",
            "semicolons optional but consistent",
            "camelCase for variables/functions",
            "PascalCase for types/interfaces/classes",
            "I-prefix for interfaces (optional, project-dependent)",
        ],
        "patterns": [
            "type Name = { field: Type }",
            "interface Name { field: Type; }",
            "generic: function<T>(arg: T): T",
            "enum Name { A, B, C }",
            "as Type for type assertion",
            "keyof, typeof, Partial<T>, Required<T>, Pick<T,K>",
            "readonly modifier",
            "union: Type1 | Type2",
            "intersection: Type1 & Type2",
            "const x: Type = value",
            "arrow functions with types: (x: number) => string",
            "import type { Name } from 'module'",
            "! non-null assertion",
            "satisfies operator",
        ],
        "error_handling": "try { } catch (err: unknown) { }",
        "string_quotes": "single quotes or backticks preferred",
        "comments": "// inline, /** */ TSDoc with @param @returns",
    },

    "c": {
        "name": "C",
        "formatting": [
            "4 spaces or tabs (project-dependent)",
            "K&R or Allman brace style (match surrounding code)",
            "snake_case for functions/variables",
            "UPPER_CASE for macros and constants",
            "pointer star with variable: int *ptr",
        ],
        "patterns": [
            "#include <header.h> / #include \"local.h\"",
            "#define MACRO value",
            "#ifdef / #ifndef / #endif guards",
            "typedef struct { } Name;",
            "malloc/calloc/realloc + free",
            "NULL for null pointers",
            "sizeof(type)",
            "pointer arithmetic: ptr++, *ptr, &var",
            "-> for pointer member access",
            ". for struct member access",
            "static for file-scope functions",
            "void* for generic pointers",
            "return 0; from main",
            "printf/fprintf/sprintf format strings",
        ],
        "error_handling": "if (ptr == NULL) { return -1; }",
        "string_quotes": "double quotes for strings, single for chars",
        "comments": "/* */ for block, // for inline (C99+)",
        "semicolons": "required after every statement",
    },

    "cpp": {
        "name": "C++",
        "formatting": [
            "4 spaces or tabs (project-dependent)",
            "K&R or Allman brace style",
            "snake_case or camelCase (project-dependent)",
            "PascalCase for classes",
            "UPPER_CASE for macros",
        ],
        "patterns": [
            "#include <header> / #include \"local.h\"",
            "namespace Name { }",
            "class Name { public: private: protected: };",
            "std::vector<T>, std::string, std::map<K,V>",
            "std::unique_ptr<T>, std::shared_ptr<T>",
            "auto for type inference",
            "range-based for: for (auto& x : container)",
            "lambda: [capture](params) { body }",
            "template<typename T>",
            "const& for read-only references",
            "std::move for move semantics",
            "override, final keywords",
            "using namespace std; (discouraged but common)",
            ":: scope resolution",
            "new/delete (prefer smart pointers)",
        ],
        "error_handling": "try { } catch (const std::exception& e) { }",
        "string_quotes": 'double quotes, R"(raw)" for raw strings',
        "comments": "// inline, /* */ block",
        "semicolons": "required after statements and class definitions",
    },

    "java": {
        "name": "Java",
        "formatting": [
            "4 spaces indentation",
            "opening brace on same line (K&R)",
            "camelCase for methods/variables",
            "PascalCase for classes",
            "UPPER_CASE for constants",
        ],
        "patterns": [
            "public class Name { }",
            "public static void main(String[] args)",
            "new ClassName()",
            "List<T>, Map<K,V>, Set<T>",
            "for (Type x : collection)",
            "@Override, @Deprecated annotations",
            "implements Interface, extends Class",
            "this. for instance members",
            "static final for constants",
            "import java.util.*;",
            "package com.example;",
            "getter/setter pattern",
            "var for local type inference (Java 10+)",
            "record Name(Type field) (Java 16+)",
            "switch expression with -> (Java 14+)",
        ],
        "error_handling": "try { } catch (ExceptionType e) { } finally { }",
        "string_quotes": "double quotes only, single for char",
        "comments": "// inline, /* */ block, /** */ Javadoc",
        "semicolons": "required after every statement",
    },

    "kotlin": {
        "name": "Kotlin",
        "formatting": [
            "4 spaces indentation",
            "opening brace on same line",
            "camelCase for functions/properties",
            "PascalCase for classes",
            "UPPER_CASE for constants",
            "no semicolons needed",
        ],
        "patterns": [
            "fun name(param: Type): ReturnType {",
            "val immutable = value",
            "var mutable = value",
            "data class Name(val field: Type)",
            "sealed class / sealed interface",
            "when (expr) { pattern -> result }",
            "?.  safe call, ?: elvis operator, !! non-null assert",
            "it implicit lambda parameter",
            "object for singletons",
            "companion object { }",
            "suspend fun for coroutines",
            "listOf(), mapOf(), mutableListOf()",
            "extension functions: fun Type.name()",
            "string templates: \"$var ${expr}\"",
            "init { } block in class",
        ],
        "error_handling": "try { } catch (e: ExceptionType) { }",
        "string_quotes": "double quotes only",
        "comments": "// inline, /* */ block, /** */ KDoc",
    },

    "ruby": {
        "name": "Ruby",
        "formatting": [
            "2 spaces indentation",
            "snake_case for methods/variables",
            "PascalCase for classes/modules",
            "UPPER_CASE for constants",
            "no semicolons",
        ],
        "patterns": [
            "def method_name(args) ... end",
            "class Name < Base ... end",
            "module Name ... end",
            "do |block_var| ... end",
            "{ |x| x.method } for single-line blocks",
            "attr_accessor :name",
            "if/unless/elsif/else/end",
            "require 'gem' / require_relative 'file'",
            "puts, print, p for output",
            "nil, true, false",
            ":symbol syntax",
            "hash: { key: value } or { :key => value }",
            "@instance, @@class, $global variables",
            "yield for blocks",
            "? and ! method suffixes",
        ],
        "error_handling": "begin ... rescue ExceptionType => e ... end",
        "string_quotes": "single or double, double for interpolation",
        "comments": "# inline, =begin/=end block",
    },

    "swift": {
        "name": "Swift",
        "formatting": [
            "4 spaces indentation",
            "opening brace on same line",
            "camelCase for functions/variables",
            "PascalCase for types/protocols",
        ],
        "patterns": [
            "func name(param: Type) -> ReturnType {",
            "let constant = value",
            "var variable = value",
            "guard let x = optional else { return }",
            "if let x = optional { }",
            "switch value { case .pattern: }",
            "struct Name { } / class Name { } / enum Name { }",
            "protocol Name { }",
            "extension Type { }",
            "init() { } for constructors",
            "Optional<T> / T? shorthand",
            "closure: { (params) -> Type in body }",
            "async/await/Task { }",
            "@Published, @State, @Binding (SwiftUI)",
            "import Foundation",
        ],
        "error_handling": "do { try expr } catch { }",
        "string_quotes": "double quotes only, string interpolation \\(var)",
        "comments": "// inline, /* */ block, /// doc",
    },

    "php": {
        "name": "PHP",
        "formatting": [
            "4 spaces indentation (PSR-12)",
            "opening brace on next line for classes, same line for methods",
            "camelCase for methods/variables",
            "PascalCase for classes",
            "UPPER_CASE for constants",
        ],
        "patterns": [
            "<?php opening tag",
            "$variable with dollar sign",
            "function name($param): ReturnType {",
            "class Name extends Base implements Interface {",
            "public/private/protected visibility",
            "-> for object member access",
            "=> for array key-value pairs",
            ":: for static access",
            "use Namespace\\Class;",
            "namespace App\\Module;",
            "array() or [] shorthand",
            "echo, print for output",
            "new ClassName()",
            "fn($x) => $x * 2 for arrow functions",
            "match($x) { pattern => result }",
        ],
        "error_handling": "try { } catch (ExceptionType $e) { }",
        "string_quotes": "single for literal, double for interpolation",
        "comments": "// inline, /* */ block, /** */ PHPDoc",
        "semicolons": "required after every statement",
    },

    "csharp": {
        "name": "C#",
        "formatting": [
            "4 spaces indentation",
            "Allman brace style (braces on own line)",
            "PascalCase for methods/properties/classes",
            "camelCase for local variables/parameters",
            "_camelCase for private fields",
        ],
        "patterns": [
            "namespace Name { } or namespace Name;",
            "class Name : Base, IInterface { }",
            "public/private/protected/internal",
            "async Task<T> MethodAsync()",
            "var for type inference",
            "properties: public Type Name { get; set; }",
            "LINQ: from x in collection select x",
            "lambda: (x) => x.Method()",
            "string interpolation: $\"{var}\"",
            "using directive / using statement",
            "nullable: Type? / int?",
            "record Name(Type Prop);",
            "pattern matching: is Type name",
            "=> expression body",
            "new() target-typed",
        ],
        "error_handling": "try { } catch (ExceptionType ex) { } finally { }",
        "string_quotes": 'double quotes, @ for verbatim, $ for interpolation',
        "comments": "// inline, /* */ block, /// XML doc",
        "semicolons": "required after every statement",
    },

    "scala": {
        "name": "Scala",
        "formatting": [
            "2 spaces indentation",
            "camelCase for methods/values",
            "PascalCase for types/objects",
        ],
        "patterns": [
            "def name(param: Type): ReturnType = {",
            "val immutable = value",
            "var mutable = value",
            "case class Name(field: Type)",
            "object Name { } for singletons",
            "trait Name { }",
            "match { case Pattern => result }",
            "Option[T], Some(x), None",
            "for (x <- collection) yield expr",
            "implicit parameters and conversions",
            "type alias: type Name = Type",
            "sealed trait for ADTs",
            "_ wildcard",
            "import package.{A, B}",
        ],
        "error_handling": "Try { expr } match { case Success(v) => case Failure(e) => }",
        "string_quotes": 'double quotes, triple """ for multiline',
        "comments": "// inline, /* */ block, /** */ Scaladoc",
    },

    "lua": {
        "name": "Lua",
        "formatting": [
            "2 spaces indentation (common)",
            "snake_case for variables/functions",
            "no semicolons needed",
        ],
        "patterns": [
            "function name(args) ... end",
            "local var = value",
            "if cond then ... elseif ... else ... end",
            "for i = 1, n do ... end",
            "for k, v in pairs(table) do ... end",
            "while cond do ... end",
            "repeat ... until cond",
            "table: { key = value }",
            "table access: t.key or t[key]",
            ".. for string concatenation",
            "# for length",
            "nil for null",
            "require('module')",
            "self:method() / self.field",
            "metatables: setmetatable(t, mt)",
        ],
        "error_handling": "pcall(func, args) / xpcall(func, handler)",
        "string_quotes": "single or double, [[ ]] for multiline",
        "comments": "-- inline, --[[ ]] block",
    },

    "shell": {
        "name": "Shell/Bash",
        "formatting": [
            "2 spaces indentation (Google style)",
            "snake_case for variables/functions",
            "UPPER_CASE for environment variables",
        ],
        "patterns": [
            "#!/bin/bash shebang",
            "var=value (no spaces around =)",
            "$var or ${var} for expansion",
            "if [ condition ]; then ... fi",
            "[[ ]] for extended test",
            "for var in list; do ... done",
            "while read -r line; do ... done",
            "case $var in pattern) ;; esac",
            "function name() { }",
            "$(command) for substitution",
            "| pipe, > redirect, >> append",
            "2>&1 stderr redirect",
            "\"$var\" always quote variables",
            "local var=value in functions",
            "set -euo pipefail for strict mode",
        ],
        "error_handling": "|| for fallback, set -e for exit on error",
        "string_quotes": "double for interpolation, single for literal",
        "comments": "# for comments",
    },

    "sql": {
        "name": "SQL",
        "formatting": [
            "UPPER_CASE for keywords (SELECT, FROM, WHERE)",
            "snake_case for table/column names",
            "indentation for sub-clauses",
        ],
        "patterns": [
            "SELECT col FROM table WHERE cond",
            "INSERT INTO table (cols) VALUES (vals)",
            "UPDATE table SET col = val WHERE cond",
            "DELETE FROM table WHERE cond",
            "JOIN types: INNER, LEFT, RIGHT, FULL",
            "GROUP BY col HAVING cond",
            "ORDER BY col ASC/DESC",
            "CREATE TABLE name ( col TYPE constraints )",
            "ALTER TABLE, DROP TABLE",
            "INDEX, PRIMARY KEY, FOREIGN KEY",
            "subqueries: (SELECT ...)",
            "CASE WHEN cond THEN val ELSE val END",
            "aggregate: COUNT, SUM, AVG, MAX, MIN",
            "NULL handling: IS NULL, COALESCE, IFNULL",
        ],
        "string_quotes": "single quotes for strings",
        "comments": "-- inline, /* */ block",
        "semicolons": "required to terminate statements",
    },

    "html": {
        "name": "HTML",
        "formatting": [
            "2 spaces indentation",
            "lowercase tag names",
            "double quotes for attributes",
        ],
        "patterns": [
            "<!DOCTYPE html>",
            "<tag attribute=\"value\">content</tag>",
            "self-closing: <br />, <img />, <input />",
            "<div>, <span>, <p>, <a href=\"\">",
            "<ul>/<ol> with <li>",
            "<table> with <tr>, <th>, <td>",
            "<form> with <input>, <select>, <textarea>",
            "class=\"name\" and id=\"name\"",
            "<script src=\"\">, <link rel=\"stylesheet\">",
            "data-* custom attributes",
            "semantic: <header>, <main>, <footer>, <section>, <article>",
        ],
        "comments": "<!-- comment -->",
    },

    "css": {
        "name": "CSS",
        "formatting": [
            "2 spaces indentation",
            "kebab-case for class names",
            "one property per line",
            "space before opening brace",
        ],
        "patterns": [
            "selector { property: value; }",
            ".class, #id, element selectors",
            "pseudo: :hover, :focus, ::before, ::after",
            "media queries: @media (condition) { }",
            "flexbox: display: flex; justify-content; align-items",
            "grid: display: grid; grid-template-columns",
            "var(--custom-property)",
            "calc() for computed values",
            "transition, animation, @keyframes",
            "position: relative/absolute/fixed/sticky",
            "z-index for stacking",
        ],
        "comments": "/* comment */",
        "semicolons": "required after every property",
    },

    "yaml": {
        "name": "YAML",
        "formatting": [
            "2 spaces indentation, NEVER tabs",
            "no trailing spaces",
        ],
        "patterns": [
            "key: value",
            "list: - item",
            "nested: indent by 2",
            "multiline: | for literal, > for folded",
            "anchors: &name / aliases: *name",
            "boolean: true/false",
            "null: null or ~",
            "quotes only when needed (special chars)",
        ],
        "comments": "# comment",
    },

    "json": {
        "name": "JSON",
        "formatting": [
            "2 spaces indentation",
            "double quotes ONLY for keys and strings",
            "no trailing commas",
            "no comments allowed",
        ],
        "patterns": [
            "{ \"key\": value }",
            "[ array, items ]",
            "types: string, number, boolean, null, object, array",
            "nested objects and arrays",
        ],
    },

    "dart": {
        "name": "Dart",
        "formatting": [
            "2 spaces indentation",
            "camelCase for variables/functions",
            "PascalCase for classes",
            "_prefix for private",
        ],
        "patterns": [
            "void main() { }",
            "var / final / const",
            "String, int, double, bool, List<T>, Map<K,V>",
            "class Name extends/implements/with",
            "Future<T>, async/await",
            "=> for expression functions",
            "?. safe navigation, ?? null-aware",
            "required named parameters: {required Type name}",
            "late for lazy init",
            "import 'package:name/file.dart';",
        ],
        "error_handling": "try { } on ExceptionType catch (e) { }",
        "string_quotes": "single quotes preferred, $ interpolation",
        "comments": "// inline, /* */ block, /// doc",
        "semicolons": "required",
    },

    "elixir": {
        "name": "Elixir",
        "formatting": [
            "2 spaces indentation",
            "snake_case for functions/variables",
            "PascalCase for modules",
        ],
        "patterns": [
            "def name(args) do ... end",
            "defp for private functions",
            "defmodule Name do ... end",
            "|> pipe operator",
            "pattern matching: = operator",
            "case/cond/with",
            "atoms: :name",
            "tuples: {a, b, c}",
            "lists: [h | t]",
            "maps: %{key: value}",
            "structs: %Name{}",
            "@module_attribute",
            "spawn, send, receive for concurrency",
        ],
        "error_handling": "try do ... rescue e -> ... end",
        "string_quotes": 'double quotes for strings, single for charlists',
        "comments": "# inline",
    },

    "haskell": {
        "name": "Haskell",
        "formatting": [
            "2 spaces indentation",
            "camelCase for functions",
            "PascalCase for types/constructors",
            "significant whitespace (layout rule)",
        ],
        "patterns": [
            "function :: Type -> Type",
            "function arg1 arg2 = expr",
            "where clause",
            "let ... in expr",
            "case expr of { Pattern -> result }",
            "do notation for monads",
            "data Type = Constructor | Constructor",
            "class Typeclass where",
            "instance Typeclass Type where",
            "import Module (names)",
            "list comprehension: [expr | x <- list, guard]",
            "$ for application, . for composition",
            "Maybe a, Either a b, IO a",
        ],
        "comments": "-- inline, {- -} block, -- | Haddock",
    },

    "cobol": {
        "name": "COBOL",
        "formatting": [
            "columns 1-6: sequence number (or blank)",
            "column 7: indicator (* for comment, - for continuation, D for debug)",
            "columns 8-11: Area A (division/section/paragraph headers, 01/77 levels)",
            "columns 12-72: Area B (statements, 02-49 levels)",
            "columns 73-80: identification (ignored by compiler)",
            "UPPER CASE for keywords (traditional, lowercase accepted in modern)",
            "period (.) terminates sentences/paragraphs",
            "HYPHEN-CASE for data names and paragraph names",
        ],
        "patterns": [
            "IDENTIFICATION DIVISION. PROGRAM-ID. name.",
            "ENVIRONMENT DIVISION. CONFIGURATION SECTION. INPUT-OUTPUT SECTION.",
            "DATA DIVISION. FILE SECTION. WORKING-STORAGE SECTION. LINKAGE SECTION.",
            "PROCEDURE DIVISION.",
            "01 RECORD-NAME. 05 FIELD-NAME PIC X(10).",
            "PIC 9(5) / PIC X(20) / PIC S9(7)V99 COMP-3",
            "MOVE source TO destination",
            "IF condition THEN ... ELSE ... END-IF",
            "PERFORM paragraph-name",
            "PERFORM VARYING idx FROM 1 BY 1 UNTIL idx > max",
            "EVALUATE TRUE WHEN condition ... END-EVALUATE",
            "READ file-name INTO record AT END ...",
            "WRITE record FROM data",
            "OPEN INPUT/OUTPUT/I-O/EXTEND file-name",
            "CLOSE file-name",
            "DISPLAY 'text' variable",
            "ACCEPT variable FROM CONSOLE",
            "ADD/SUBTRACT/MULTIPLY/DIVIDE ... GIVING result",
            "COMPUTE result = expression",
            "STRING ... DELIMITED BY ... INTO target",
            "UNSTRING source DELIMITED BY ',' INTO f1 f2 f3",
            "CALL 'program-name' USING param1 param2",
            "COPY copybook-name.",
            "88 level condition names (boolean flags)",
            "REDEFINES for union-like overlays",
            "OCCURS n TIMES for arrays",
            "STOP RUN. / GOBACK.",
        ],
        "error_handling": "ON SIZE ERROR / NOT ON SIZE ERROR, FILE STATUS checking",
        "string_quotes": "single quotes (apostrophes) for literals: 'Hello'",
        "comments": "* in column 7 for full-line comment, *> for inline (COBOL 2002+)",
        "semicolons": "period (.) terminates paragraphs and sentences",
    },

    "zig": {
        "name": "Zig",
        "formatting": [
            "4 spaces indentation",
            "camelCase for functions",
            "PascalCase for types",
            "SCREAMING_SNAKE for comptime constants",
        ],
        "patterns": [
            "fn name(param: type) type {",
            "const / var declarations",
            "if (cond) |val| { } else { }",
            "for (slice) |item| { }",
            "while (cond) : (continue_expr) { }",
            "switch (expr) { .tag => value }",
            "try / catch |err| { }",
            "orelse for optional unwrap",
            "comptime for compile-time execution",
            "@import(\"std\")",
            "error union: !T",
            "optional: ?T",
            "slices: []const u8",
            "allocator pattern",
        ],
        "error_handling": "fn() !void / try expr / catch",
        "string_quotes": 'double quotes, no single quotes',
        "comments": "// inline, /// doc",
    },

    "vue": {
        "name": "Vue",
        "formatting": [
            "2 spaces indentation",
            "PascalCase for components",
            "kebab-case in templates",
        ],
        "patterns": [
            "<template> ... </template>",
            "<script setup> ... </script>",
            "<style scoped> ... </style>",
            "ref(), reactive(), computed()",
            "v-if, v-for, v-bind (:), v-on (@)",
            "{{ interpolation }}",
            "defineProps(), defineEmits()",
            "onMounted(), watch(), watchEffect()",
            "<component :is=\"\">",
            "<slot name=\"\">",
        ],
        "comments": "<!-- HTML --> // JS /* CSS */",
    },

    "svelte": {
        "name": "Svelte",
        "formatting": [
            "2 spaces indentation (Prettier)",
            "PascalCase for components",
        ],
        "patterns": [
            "<script> ... </script>",
            "<style> ... </style>",
            "{#if cond} ... {:else} ... {/if}",
            "{#each items as item} ... {/each}",
            "$: reactive declarations",
            "on:event={handler}",
            "bind:value={var}",
            "export let prop;",
            "{@html rawHtml}",
            "transition:fade",
        ],
        "comments": "<!-- HTML --> // JS /* CSS */",
    },

    "r": {
        "name": "R",
        "formatting": [
            "2 spaces indentation",
            "snake_case or dot.case for functions",
            "<- for assignment (preferred over =)",
        ],
        "patterns": [
            "function(args) { }",
            "library(package)",
            "data.frame, tibble",
            "pipe: %>% or |>",
            "c() for vectors",
            "list() for lists",
            "apply/sapply/lapply family",
            "if (cond) { } else { }",
            "for (x in seq) { }",
            "NULL, NA, TRUE, FALSE",
            "$ for column access",
            "dplyr: select, filter, mutate, summarize",
            "ggplot() + geom_*()",
        ],
        "error_handling": "tryCatch(expr, error = function(e) { })",
        "string_quotes": "double or single",
        "comments": "# comment",
    },

    "ocaml": {
        "name": "OCaml",
        "formatting": [
            "2 spaces indentation",
            "snake_case for values/functions",
            "PascalCase for modules/constructors",
        ],
        "patterns": [
            "let name = expr",
            "let rec name = expr (recursive)",
            "fun x -> expr (lambda)",
            "match expr with | Pattern -> result",
            "type name = Constructor of type",
            "module Name = struct ... end",
            "sig ... end for signatures",
            "if cond then expr else expr",
            "List.map, List.filter, List.fold_left",
            "option type: Some x | None",
            "result type: Ok x | Error e",
            "ref, !, := for mutable",
            ";; for top-level evaluation",
        ],
        "error_handling": "try expr with exn -> handler",
        "string_quotes": "double quotes only",
        "comments": "(* block comment *)",
    },

    "latex": {
        "name": "LaTeX",
        "formatting": [
            "2 spaces indentation for environments",
            "one sentence per line (preferred)",
        ],
        "patterns": [
            "\\command{argument}",
            "\\begin{environment} ... \\end{environment}",
            "\\section{}, \\subsection{}, \\chapter{}",
            "\\label{}, \\ref{}, \\cite{}",
            "$ inline math $, $$ display $$, \\[ \\]",
            "\\frac{}{}, \\sum_{}, \\int_{}^{}",
            "\\textbf{}, \\textit{}, \\emph{}",
            "\\usepackage{name}",
            "\\documentclass{article}",
            "itemize/enumerate with \\item",
            "\\newcommand{\\name}[args]{def}",
        ],
        "comments": "% line comment",
    },

    "markdown": {
        "name": "Markdown",
        "formatting": [
            "blank line before headings",
            "blank line before/after code blocks",
            "consistent list markers (- or *)",
        ],
        "patterns": [
            "# H1, ## H2, ### H3",
            "**bold**, *italic*, `code`",
            "```language for code blocks",
            "[text](url) for links",
            "![alt](url) for images",
            "- or * for unordered lists",
            "1. for ordered lists",
            "> blockquote",
            "--- for horizontal rule",
            "| table | header |",
        ],
    },

    "toml": {
        "name": "TOML",
        "formatting": [
            "no indentation needed",
            "blank line between sections",
        ],
        "patterns": [
            "[section]",
            "[[array-of-tables]]",
            "key = \"value\"",
            "integers, floats, booleans, dates",
            "arrays: [1, 2, 3]",
            "inline tables: { key = val }",
            "multiline strings: triple quotes",
        ],
        "comments": "# comment",
    },
}


def get_lexicon(lang: str) -> dict | None:
    """Get lexicon for a language. Tries exact match, then aliases."""
    if lang in LEXICONS:
        return LEXICONS[lang]

    # Aliases
    aliases = {
        'js': 'javascript', 'jsx': 'javascript', 'mjs': 'javascript',
        'ts': 'typescript', 'tsx': 'typescript',
        'rs': 'rust',
        'py': 'python', 'pyx': 'python', 'pyi': 'python',
        'c++': 'cpp', 'cc': 'cpp', 'cxx': 'cpp', 'hpp': 'cpp',
        'c#': 'csharp', 'cs': 'csharp',
        'sh': 'shell', 'bash': 'shell', 'zsh': 'shell',
        'kt': 'kotlin', 'kts': 'kotlin',
        'rb': 'ruby',
        'ex': 'elixir', 'exs': 'elixir',
        'hs': 'haskell',
        'ml': 'ocaml', 'mli': 'ocaml',
        'tex': 'latex',
        'md': 'markdown',
        'yml': 'yaml',
        'htm': 'html',
        'scss': 'css', 'sass': 'css', 'less': 'css',
        'v': 'vue',
        'cob': 'cobol', 'cbl': 'cobol', 'cpy': 'cobol',
    }

    normalized = lang.lower().strip().lstrip('.')
    return LEXICONS.get(aliases.get(normalized, normalized))


def format_lexicon_prompt(lang: str) -> str:
    """Format a lexicon as a prompt section for the LLM."""
    lex = get_lexicon(lang)
    if not lex:
        return ""

    parts = [f"=== {lex['name']} LANGUAGE RULES ==="]

    if 'formatting' in lex:
        parts.append("FORMATTING:")
        for rule in lex['formatting']:
            parts.append(f"  - {rule}")

    if 'patterns' in lex:
        parts.append("SYNTAX PATTERNS:")
        for pattern in lex['patterns']:
            parts.append(f"  - {pattern}")

    if 'error_handling' in lex:
        parts.append(f"ERROR HANDLING: {lex['error_handling']}")

    if 'string_quotes' in lex:
        parts.append(f"QUOTES: {lex['string_quotes']}")

    if 'comments' in lex:
        parts.append(f"COMMENTS: {lex['comments']}")

    if 'semicolons' in lex:
        parts.append(f"SEMICOLONS: {lex['semicolons']}")

    parts.append("=== END RULES ===")
    return "\n".join(parts)


# Quick stats
TOTAL_LANGUAGES = len(LEXICONS)
TOTAL_RULES = sum(
    len(lex.get('formatting', [])) + len(lex.get('patterns', []))
    for lex in LEXICONS.values()
)
