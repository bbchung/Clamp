from neovim import attach
from clang import cindex
import compilation_database
import clamp_helper
import sys


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
    _is_running = True

    context = {}  # {'filepath' : [tu, tick]}

    # nvim = attach('stdio')
    nvim = attach('socket', path=sys.argv[1])
    nvim.command('let g:clamp_channel=%d' % nvim.channel_id)
    print 'channel=%d' % nvim.channel_id

    cindex.Config.set_library_file(nvim.vars['clamp_libclang_path'])
    print 'libclang=%s' % cindex.Config.library_file

    occurrences_pri = nvim.vars['clamp_occurrence_priority']
    syntax_pri = nvim.vars['clamp_syntax_priority']

    _parse.idx = cindex.Index.create()
    _parse.cdb = compilation_database.CompilationDatabase.from_dir(
        nvim.call('getcwd'), nvim.vars['clamp_heuristic_compile_args'])
    _parse.global_args = nvim.vars['clamp_compile_args']

    _highlight.blacklist = nvim.vars['clamp_highlight_blacklist']

    nvim.call('ClampNotifyParseHighlight')

    unsaved = []
    while (_is_running):
        event = nvim.session.next_message()
        if not event:
            continue

        print 'event', event[1]
        if event[1] == 'parse&highlight':
            filepath = event[2][0]
            begin_line = event[2][1]
            end_line = event[2][2]

            changedtick = nvim.eval('b:changedtick')
            for buffer in nvim.buffers:
                if buffer.name == filepath:
                    _update_unsaved(buffer, unsaved)
                    _parse_or_reparse_if_need(buffer.name, unsaved, context, changedtick);

                    tu, tick = context[filepath]
                    symbol = clamp_helper.get_vim_symbol(
                        nvim, clamp_helper.get_vim_cursor(nvim, tu))
                    syntax, occurrence = _highlight(
                        tu, filepath, begin_line, end_line, symbol)

                    nvim.call('ClampHighlight', filepath, [
                              [syntax_pri, syntax], [occurrences_pri, occurrence]])

                    break

        elif event[1] == 'parse':
            filepath = event[2][0]
            changedtick = nvim.eval('b:changedtick')

            for buffer in nvim.buffers:
                if buffer.name == filepath:
                    _update_unsaved(buffer, unsaved)
                    _parse_or_reparse_if_need(buffer.name, unsaved, context, changedtick);

                    break

        elif event[1] == 'highlight':
            filepath = event[2][0]
            begin_line = event[2][1]
            end_line = event[2][2]

            for buffer in nvim.buffers:
                if buffer.name == filepath:
                    tu, tick = context[filepath]

                    symbol = clamp_helper.get_vim_symbol(
                        nvim, clamp_helper.get_vim_cursor(nvim, tu))
                    syntax, occurrence = _highlight(
                        tu, filepath, begin_line, end_line, symbol)

                    nvim.call('ClampHighlight', filepath, [
                              (syntax_pri, syntax), (occurrences_pri, occurrence)])


        elif event[1] == 'rename':
            filepath = event[2][0]
            row = event[2][1]
            col = event[2][2]

            _update_unsaved_and_parse_all(nvim, unsaved, context)

            cursor = clamp_helper.get_cursor(context[filepath][0], filepath, row, col)
            if not cursor:
                event[3].send({})
                continue

            symbol = clamp_helper.get_semantic_symbol(cursor)
            if not symbol:
                event[3].send({})
                continue

            usr = symbol.get_usr()

            result = {'old':symbol.spelling, 'renames':{}}
            symbols = []
            for filepath, [tu, tick] in context.iteritems() :
                clamp_helper.search_cursor_by_usr(tu.cursor, usr, symbols)
                if not symbols:
                    continue

                locations = []
                for sym in symbols:                                                                                                                                                                                                                                
                    clamp_helper.search_referenced_tokens(tu, sym, locations)      

                result['renames'][filepath] = locations

            event[3].send(result);

        elif event[1] == 'shutdown':
            nvim.call('Shutdown')
            nvim.session.stop()
            _is_running = False
            event[3].send('ok')


def _parse(unsaved, filepath):
    args = None
    if _parse.cdb:
        args = _parse.cdb.get_useful_args(filepath) + _parse.global_args

    return _parse.idx.parse(filepath, args, unsaved, options=cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)

def _update_unsaved(vim_buffer, unsaved):
    for filepath, buffer in unsaved:
        if filepath == vim_buffer.name:
            unsaved.remove((filepath, buffer))

    unsaved.append((vim_buffer.name, '\n'.join(vim_buffer)))

def _update_unsaved_and_parse_all(nvim, unsaved, context):
    unsaved = []

    for buffer in nvim.buffers:
        unsaved.append((buffer.name, '\n'.join(buffer)))

    for buffer in nvim.buffers:
        _parse_or_reparse_if_need(buffer.name, unsaved, context, nvim.call('getbufvar', buffer.name, 'changedtick'));

def _parse_or_reparse_if_need(filepath, unsaved, context, changedtick):
    if filepath not in context:
        context[filepath] = [_parse(unsaved, filepath), changedtick]
    elif context[filepath][1] != changedtick:
        context[filepath][0].reparse(unsaved, options=cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)
        context[filepath][1] = changedtick

def _highlight(tu, filepath, begin_line, end_line, symbol):
    file = tu.get_file(filepath)

    if not file:
        return None, None

    begin = cindex.SourceLocation.from_position(
        tu, file, line=begin_line, column=1)
    end = cindex.SourceLocation.from_position(
        tu, file, line=end_line + 1, column=1)
    tokens = tu.get_tokens(
        extent=cindex.SourceRange.from_locations(begin, end))

    syntax = {}
    occurrence = {'clampOccurrences': []}

    for token in tokens:
        if token.kind.value != 2:  # no keyword, comment
            continue

        cursor = token.cursor
        cursor._tu = tu

        pos = [token.location.line, token.location.column, len(token.spelling)]
        group = _get_syntax_group(
            cursor.kind,
            cursor.type.kind,
            _highlight.blacklist)

        if group:
            if group not in syntax:
                syntax[group] = []

            syntax[group].append(pos)

        token_symbol = clamp_helper.get_semantic_symbol(cursor)
        if symbol and token_symbol and symbol == token_symbol and token.spelling == token_symbol.spelling:
            occurrence['clampOccurrences'].append(pos)

    return syntax, occurrence

engine_start()
