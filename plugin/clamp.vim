if !has('nvim')
    echohl WarningMsg |
                \ echomsg 'Clamp unavailable: requires neovim' |
                \ echohl None
    finish
endif

if exists('g:loaded_clamp')
    finish
endif

let s:script_folder_path = escape( expand( '<sfile>:p:h' ), '\' )
execute('source '. s:script_folder_path . '/../syntax/clamp.vim')

fun! ClampHighlight(filepath, highlights)
    if a:filepath != expand('%:p')  
        return
    endif

    for [priority, matches] in a:highlights
        for m in getmatches()
            if priority == m['priority']
                call matchdelete(m['id'])
            endif
        endfor

        for [group, all_pos] in items(matches)
            let s:count = 0
            let s:match8 = []

            for pos in all_pos
                call add(s:match8, pos)
                let s:count = s:count + 1
                if s:count == 8
                    call matchaddpos(group, s:match8, priority)

                    let s:count = 0
                    let s:match8 = []
                endif
            endfor

            call matchaddpos(group, s:match8, priority)
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
    for m in getmatches()
        if index(a:priorities, m['priority']) >= 0
            call matchdelete(m['id'])
        endif
    endfor
endf

fun! s:enable_clamp()
    call s:request_shutdown()
    "let g:clamp_channel = rpcstart('python', [s:script_folder_path.'/../python/engine.py', v:servername])
    let s:clamp_job = jobstart('python '.s:script_folder_path.'/../python/engine.py '.v:servername)
endf

fun! s:request_shutdown()
    if exists('g:clamp_channel')
        silent! call rpcrequest(g:clamp_channel, 'shutdown')
    endif

    if exists('s:clamp_job')
        call jobstop(s:clamp_job)
        silent! unlet s:clamp_job
    endif
endf

fun! ClampNotifyParseHighlight()
    if index(['c', 'cpp', 'objc', 'objcpp'], &ft) == -1
        return
    endif

    if exists('g:clamp_channel')
        silent! call rpcnotify(g:clamp_channel, 'parse&highlight', expand('%:p'), b:changedtick, getline(1,'$'), line('w0'), line('w$'))
    endif
endf

fun! ClampNotifyParse()
    if index(['c', 'cpp', 'objc', 'objcpp'], &ft) == -1
        return
    endif

    if exists('g:clamp_channel')
        silent! call rpcnotify(g:clamp_channel, 'parse', expand('%:p'), b:changedtick, getline(1,'$'))
    endif
endf

fun! ClampNotifyHighlight()
    if index(['c', 'cpp', 'objc', 'objcpp'], &ft) == -1
        return
    endif

    if exists('g:clamp_channel')
        silent! call rpcnotify(g:clamp_channel, 'highlight', expand('%:p'), line('w0'), line('w$'))
    endif
endf



let g:clamp_occurrence_priority = get(g:, 'clamp_occurrence_priority', 2)
let g:clamp_syntax_priority = get(g:, 'clamp_syntax_priority', 1)
let g:clamp_autostart = get(g:, 'clamp_autostart', 1)
let g:clamp_libclang_path = get(g:, 'clamp_libclang_path', '')
let g:clamp_rename_prompt_level = get(g:, 'clamp_rename_prompt_level', 1)
let g:clamp_enable_cross_rename = get(g:, 'clamp_enable_cross_rename', 1)
let g:clamp_highlight_blacklist = get(g:, 'clamp_highlight_blacklist', ['clampInclusionDirective'])
let g:clamp_heuristic_compile_args = get(g:, 'clamp_heuristic_compile_args', 1)
let g:clamp_compile_args = get(g:, 'clamp_compile_args', [])

command! ClampStart call s:enable_clamp()
command! ClampShutdown call s:request_shutdown()

if g:clamp_autostart
    au VimEnter * call s:enable_clamp()
endif
au VimLeave * silent! call s:request_shutdown()
au TextChanged * call ClampNotifyParseHighlight()
au CursorMoved * call ClampNotifyHighlight()
au TextChangedI * call ClampNotifyParse()

let g:loaded_clamp=1
