from clang import cindex


def get_semantic_symbol_from_location(tu, filepath, row, col):
    cursor = cindex.Cursor.from_location(
        tu,
        cindex.SourceLocation.from_position(tu,
                                            tu.get_file(filepath),
                                            row,
                                            col))
    if not cursor:
        return None

    tokens = cursor.get_tokens()
    for token in tokens:
        if token.kind.value == 2 and row == token.location.line and token.location.column <= col and col < token.location.column + len(token.spelling):
            return get_semantic_symbol(cursor)

    return None


def is_vim_buffer_allowed(buf):
    return buf.options['filetype'] in ["c", "cpp", "objc", "objcpp"]


def is_global_symbol(symbol):
    return symbol.kind.is_preprocessing(
    ) or symbol.semantic_parent.kind != cindex.CursorKind.FUNCTION_DECL


def search_cursor_by_usr(cursor, usr, result):
    if cursor.get_usr() == usr and cursor not in result:
        result.append(cursor)

    for c in cursor.get_children():
        search_cursor_by_usr(c, usr, result)


def get_semantic_symbol(cursor):
    if not cursor:
        return None

    if cursor.kind == cindex.CursorKind.MACRO_DEFINITION:
        return cursor

    symbol = cursor.get_definition()
    if not symbol:
        symbol = cursor.referenced

    if not symbol:
        return None

    if symbol.kind == cindex.CursorKind.CONSTRUCTOR or symbol.kind == cindex.CursorKind.DESTRUCTOR:
        symbol = symbol.semantic_parent

    return symbol


def get_spelling_or_displayname(cursor):
    return cursor.spelling if cursor.spelling else cursor.displayname


def search_referenced_tokens_by_usr(tu, usr, result, spelling):
    tokens = tu.cursor.get_tokens()
    for token in tokens:
        cursor = token.cursor
        cursor._tu = tu

        symbol = get_semantic_symbol(cursor)
        if token.spelling == spelling and symbol and symbol.get_usr() == usr:
            result.append((token.location.line, token.location.column))


def search_referenced_tokens(tu, symbol, result):
    tokens = tu.cursor.get_tokens()

    for t in tokens:
        if t.kind.value != 2:
            continue

        t_cursor = t.cursor
        t_cursor._tu = tu

        t_symbol = get_semantic_symbol(t_cursor)

        if t_symbol and t_symbol == symbol:
            result.append((t.location.line, t.location.column))
