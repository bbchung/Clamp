if !has('nvim')
    echohl WarningMsg |
                \ echomsg 'Clamp unavailable: requires neovim' |
                \ echohl None
    finish
endif

if exists('g:loaded_clamp')
    finish
endif

let s:script_folder_path = escape( expand( '<sfile>:p:h' ), '\'   )
execute('source '. s:script_folder_path . '/../syntax/clamp.vim')

fun! ClampHighlight(bufname, highlights)
    if a:bufname != expand('%:p')
        return
    endif

    for [l:priority, l:matches] in a:highlights
        for l:m in getmatches()
            if l:priority == l:m['priority']
                call matchdelete(l:m['id'])
            endif
        endfor

        for [l:group, l:all_pos] in items(l:matches)
            let s:count = 0
            let s:match8 = []

            for l:pos in l:all_pos
                call add(s:match8, l:pos)
                let s:count = s:count + 1
                if s:count == 8
                    call matchaddpos(l:group, s:match8, l:priority)

                    let s:count = 0
                    let s:match8 = []
                endif
            endfor

            call matchaddpos(l:group, s:match8, l:priority)
        endfor
    endfor
endf

fun! Shutdown()
    let a:wnr = winnr()
    windo call s:clear_match_by_priorities([g:clamp_occurrence_priority, g:clamp_syntax_priority])
    exe a:wnr.'wincmd w'

    silent! unlet g:clamp_channel

endf

fun! s:clear_match_by_priorities(priorities)
    for l:m in getmatches()
        if index(a:priorities, l:m['priority']) >= 0
            call matchdelete(l:m['id'])
        endif
    endfor
endf

fun! s:start_clamp()
    call s:request_shutdown()
    let g:clamp_channel = rpcstart('python', [s:script_folder_path.'/../python/engine.py'])
    "let g:clamp_channel = jobstart('python '.s:script_folder_path.'/../python/engine.py '.v:servername)
    call ClampNotifyParse()
    call ClampNotifyHighlight()
endf

fun! s:request_shutdown()
    if exists('g:clamp_channel')
        silent! call rpcrequest(g:clamp_channel, 'shutdown')
        call rpcstop(g:clamp_channel)
    endif

    call Shutdown()
endf

fun! ClampNotifyHighlight()
    if index(['c', 'cpp', 'objc', 'objcpp'], &filetype) == -1
        return
    endif

    if !exists('b:highlight_tick')
        let b:highlight_tick = 0
    endif

    let b:highlight_tick = b:highlight_tick + 1

    if exists('g:clamp_channel')
        let s:pos = getpos('.')
        silent! call rpcnotify(g:clamp_channel, 'highlight', expand('%:p'), line('w0'), line('w$'), s:pos[1], s:pos[2], b:highlight_tick)
    endif
endf

fun! ClampNotifyParse()
    if index(['c', 'cpp', 'objc', 'objcpp'], &filetype) == -1
        return
    endif

    if exists('g:clamp_channel')
        silent! call rpcnotify(g:clamp_channel, 'parse', bufnr(''), b:changedtick)
    endif
endf

fun! ClampCursorInfo()
    if !exists('g:clamp_channel')
        return
    endif

    let s:pos = getpos('.')
    let s:result = rpcrequest(g:clamp_channel, 'cursor_info', expand('%:p'), s:pos[1], s:pos[2])

    echo s:result
endf

fun! ClampRename()
    if !exists('g:clamp_channel')
        return
    endif
    let s:pos = getpos('.')
    let s:result = rpcrequest(g:clamp_channel, 'rename', expand('%:p'), s:pos[1], s:pos[2])
    if empty(s:result) || empty(s:result['renames'])
        return
    endif

    let s:old = s:result['old']
    echohl WildMenu
    let s:new = input('Rename ' . s:old . ' : ', s:old)
    echohl None
    if (empty(s:new) || s:old == s:new)
        return
    endif

    let l:wnr = winnr()
    let l:bufnr = bufnr('')
    let l:qflist = []
    bufdo! call s:clamp_replace(s:result['renames'], s:old, s:new, l:qflist)
    exe l:wnr.'wincmd w'
    exe 'buffer '.l:bufnr
    call setqflist(l:qflist)

endf

fun! s:clamp_replace(renames, old, new, qflist)
    if (!has_key(a:renames, expand('%:p')) || empty(a:renames[expand('%:p')]))
        return
    endif
    let l:locations = a:renames[expand('%:p')]

    let l:choice = confirm("rename '". a:old ."' to '" .a:new. "' in " .expand('%:p'). "?", "&Yes\n&No", 1)
    if (l:choice == 2)
        return
    endif

    let l:pattern = ''
    for [l:row, l:col] in l:locations
        if (!empty(l:pattern))
            let l:pattern = l:pattern . '\|'
        endif

        let l:pattern = l:pattern . '\%' . l:row . 'l' . '\%>' . (l:col - 1) . 'c\%<' . (l:col + strlen(a:old)) . 'c' . a:old
        call add(a:qflist, {'filename':bufname(''), 'bufnr':bufnr(''), 'lnum':l:row, 'text':"'".a:old."' was renamed to '".a:new."'"})
    endfor

    let l:cmd = '%s/' . l:pattern . '/' . a:new . '/gI'

    execute(l:cmd)
    copen
endf



let g:clamp_occurrence_priority = get(g:, 'clamp_occurrence_priority', -1)
let g:clamp_syntax_priority = get(g:, 'clamp_syntax_priority', -2)
let g:clamp_autostart = get(g:, 'clamp_autostart', 1)
let g:clamp_libclang_path = get(g:, 'clamp_libclang_path', '')
let g:clamp_highlight_blacklist = get(g:, 'clamp_highlight_blacklist', ['clampInclusionDirective'])
let g:clamp_heuristic_compile_args = get(g:, 'clamp_heuristic_compile_args', 1)
let g:clamp_compile_args = get(g:, 'clamp_compile_args', [])
let g:clamp_highlight_mode = get(g:, 'clamp_highlight_mode', 0)

command! ClampStart call s:start_clamp()
command! ClampShutdown call s:request_shutdown()

augroup Clamp
if g:clamp_autostart
    au VimEnter *.c,*.cpp,*.h,*.hpp call s:start_clamp()
endif
au VimLeave * silent! call s:request_shutdown()
au BufEnter,InsertLeave,TextChanged * call ClampNotifyParse()
au CursorMoved * call ClampNotifyHighlight()
if (g:clamp_highlight_mode == 1)
    au TextChangedI * call ClampNotifyParse()
endif
augroup END

let g:loaded_clamp=1
