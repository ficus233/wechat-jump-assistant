"""Restore physical screenshot geometry without silently mixing pixel scales."""
import native

def standardize_window(hwnd,cfg):
    expected=cfg.get('standard_client_size',cfg['model']['signature'][:2])
    before=native.geometry(hwnd)
    # Keep actual monitor DPI in the data signature; physical client pixels are exact.
    after=native.restore_client_size(hwnd,int(expected[0]),int(expected[1]),before['dpi'])
    return after,dict(before=before,after=after,expected_client_size=list(expected),
        dpi_matches_original=after['dpi']==cfg['model']['signature'][2])
