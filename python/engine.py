from neovim import attach
from clang import cindex
import compilation_database
import clamp_helper
import sys

_is_running = False
nvim = None
context = {}  # {'filepath' : (tu, tick)}
idx = None
cdb = None
global_args = None
blacklist = None

CUSTOM_SYNTAX_GROUP = {
    cindex.CursorKind.INCLUSION_DIRECTIVE: 'clampInclusionDirective',
    cindex.CursorKind.MACRO_INSTANTIATION: 'clampMacroInstantiation',
    cindex.CursorKind.VAR_DECL: 'clampVarDecl',
    cindex.CursorKind.STRUCT_DECL: 'clampStructDecl',
    cindex.CursorKind.UNION_DECL: 'clampUnionDecl',
    cindex.CursorKind.CLASS_DECL: 'clampClassDecl',
    cindex.CursorKind.ENUM_DECL: 'clampEnumDecl',
    cindex.CursorKind.PARM_DECL: 'clampParmDecl',
    cindex.CursorKind.FUNCTION_DECL: 'clampFunctionDecl',
    cindex.CursorKind.FUNCTION_TEMPLATE: 'clampFunctionDecl',
    cindex.CursorKind.CXX_METHOD: 'clampFunctionDecl',
    cindex.CursorKind.CONSTRUCTOR: 'clampFunctionDecl',
    cindex.CursorKind.DESTRUCTOR: 'clampFunctionDecl',
    cindex.CursorKind.FIELD_DECL: 'clampFieldDecl',
    cindex.CursorKind.ENUM_CONSTANT_DECL: 'clampEnumConstantDecl',
    cindex.CursorKind.NAMESPACE: 'clampNamespace',
    cindex.CursorKind.CLASS_TEMPLATE: 'clampClassDecl',
    cindex.CursorKind.TEMPLATE_TYPE_PARAMETER: 'clampTemplateTypeParameter',
    cindex.CursorKind.TEMPLATE_NON_TYPE_PARAMETER: 'clampTemplateNoneTypeParameter',
    cindex.CursorKind.TYPE_REF: 'clampTypeRef',  # class ref
    cindex.CursorKind.NAMESPACE_REF: 'clampNamespaceRef',  # namespace ref
    cindex.CursorKind.TEMPLATE_REF: 'clampTemplateRef',  # template class ref
    cindex.CursorKind.DECL_REF_EXPR:
    {
        cindex.TypeKind.FUNCTIONPROTO: 'clampDeclRefExprCall',  # function call
        cindex.TypeKind.ENUM: 'clampDeclRefExprEnum',  # enum ref
        cindex.TypeKind.TYPEDEF: 'clampTypeRef',  # ex: cout
    },
    cindex.CursorKind.MEMBER_REF: 'clampDeclRefExprCall',  # ex: designated initializer
    cindex.CursorKind.MEMBER_REF_EXPR:
    {
        cindex.TypeKind.UNEXPOSED: 'clampMemberRefExprCall',  # member function call
    },
}

def _get_default_syn(cursor_kind):
    if cursor_kind.is_preprocessing():
        return 'clampPrepro'
    elif cursor_kind.is_declaration():
        return 'clampDecl'
    elif cursor_kind.is_reference():
        return 'clampRef'
    else:
        return None


def _get_syntax_group(cursor_kind, type_kind, blacklist):
    group = _get_default_syn(cursor_kind)

    custom = CUSTOM_SYNTAX_GROUP.get(cursor_kind)
    if custom:
        if cursor_kind == cindex.CursorKind.DECL_REF_EXPR:
            custom = custom.get(type_kind)
            if custom:
                group = custom
        elif cursor_kind == cursor_kind == cindex.CursorKind.MEMBER_REF_EXPR:
            custom = custom.get(type_kind)
            if custom:
                group = custom
            else:
                group = 'clampMemberRefExprVar'
        else:
            group = custom

    if group in blacklist:
        return None

    return group


def engine_start():
    global _is_running
    global nvim
    global idx
    global cdb
    global global_args
    global blacklist

    _is_running = True
    nvim = attach('socket', path=sys.argv[1])
    nvim.command('let g:clamp_channel=%d' % nvim.channel_id)
    cindex.Config.set_library_file(nvim.vars['clamp_libclang_path'])
    idx = cindex.Index.create()
    cdb = compilation_database.CompilationDatabase.from_dir(nvim.call('getcwd'), nvim.vars['clamp_heuristic_compile_args'])
    highlight.occurrences_pri = nvim.vars['clamp_occurrence_priority']
    highlight.syntax_pri = nvim.vars['clamp_syntax_priority']
    blacklist = nvim.vars['clamp_highlight_blacklist']
    global_args = nvim.vars['clamp_compile_args']
    print 'channel=%d' % nvim.channel_id
    print 'libclang=%s' % nvim.vars['clamp_libclang_path']
    nvim.call('ClampNotifyParseHighlight')

    while (_is_running):
        event = nvim.session.next_message()
        print event
        if event[1] == 'parse&highlight':
            filepath = event[2][0]
            begin_line = event[2][1]
            end_line = event[2][2]

            changedtick = int(nvim.eval('b:changedtick'))
            if filepath not in context or context[filepath][1] != changedtick:
                unsaved = []
                for buffer in nvim.buffers:
                    unsaved.append((buffer.name, '\n'.join(buffer)))

                parse(unsaved, filepath, changedtick)

            tu, tick = context[filepath]
            highlight(tu, filepath, begin_line, end_line)
        elif event[1] == 'shutdown':
            nvim.call('Shutdown')
            nvim.session.stop()
            _is_running = False


def parse(unsaved, filepath, changedtick):
    global idx
    global context
    global cdb
    global global_args

    args = None
    if cdb:
        args = cdb.get_useful_args(filepath) + global_args

    new_tu = idx.parse(
        filepath,
        args,
     unsaved,
     options=cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)
    context[filepath] = (new_tu, changedtick)

def highlight(tu, filepath, begin_line, end_line):
    global nvim
    global blacklist

    file = tu.get_file(filepath)
    begin = cindex.SourceLocation.from_position(
        tu, file, line=begin_line, column=1)
    end = cindex.SourceLocation.from_position(
        tu, file, line=end_line + 1, column=1)
    tokens = tu.get_tokens(
        extent=cindex.SourceRange.from_locations(begin, end))

    syntax = {}
    occurrence = {'clampOccurrences':[]}

    symbol = clamp_helper.get_vim_symbol(nvim, clamp_helper.get_vim_cursor(nvim, tu))

    for token in tokens:
        if token.kind.value != 2:  # no keyword, comment
            continue

        cursor = token.cursor
        cursor._tu = tu

        pos = [token.location.line, token.location.column, len(token.spelling)]
        group = _get_syntax_group(cursor.kind, cursor.type.kind, blacklist)

        if group:
            if group not in syntax:
                syntax[group] = []

            syntax[group].append(pos)

        token_symbol = clamp_helper.get_semantic_symbol(cursor)
        if symbol and token_symbol and symbol == token_symbol and token.spelling == token_symbol.spelling:
            occurrence['clampOccurrences'].append(pos)

    nvim.call('ClampHighlight', filepath, syntax, highlight.syntax_pri)
    nvim.call('ClampHighlight', filepath, occurrence, highlight.occurrences_pri)


engine_start()
