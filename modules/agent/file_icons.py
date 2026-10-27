"""Shared, escaped file presentation for composer, user and assistant cards."""
import html


def split_filename(name):
    """Keep familiar compound extensions intact; a dotfile has no extension."""
    compounds = ('.tar.gz', '.tar.bz2', '.tar.xz', '.tar.zst', '.tar.lzma', '.tar.lz', '.d.ts')
    for suffix in compounds:
        if name.lower().endswith(suffix) and len(name) > len(suffix):
            return name[:-len(suffix)], name[-len(suffix):]
    dot = name.rfind('.')
    return (name[:dot], name[dot:]) if 0 < dot < len(name) - 1 else (name, '')


FILE_KINDS = {
    'text': ('txt', 'md', 'markdown', 'rtf', 'log'),
    'document': ('doc', 'docx', 'odt'),
    'pdf': ('pdf',),
    'sheet': ('csv', 'tsv', 'xls', 'xlsx', 'ods'),
    'slides': ('ppt', 'pptx', 'odp'),
    'image': ('png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'tiff', 'ico', 'heic'),
    'code': ('py', 'js', 'jsx', 'ts', 'tsx', 'd.ts', 'json', 'html', 'css', 'xml', 'yaml', 'yml', 'sh', 'sql', 'ipynb'),
    'archive': ('zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz', 'tar.gz', 'tar.bz2', 'tar.xz', 'tar.zst', 'tar.lzma', 'tar.lz'),
    'media': ('mp3', 'wav', 'ogg', 'flac', 'm4a', 'mp4', 'mov', 'avi', 'webm', 'mkv'),
}
_EXTENSION_KIND = {extension: kind for kind, extensions in FILE_KINDS.items() for extension in extensions}


def file_extension(name):
    return split_filename(name)[1][1:].upper()


def file_type_label(name):
    extension = file_extension(name) or 'FILE'
    return extension if len(extension) <= 5 else extension[:5] + '…'


def file_size_label(size):
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        return '大小待确认'
    divisor, unit = (1024 ** 3, 'GB') if size >= 1024 ** 3 else ((1024 ** 2, 'MB') if size >= 1024 ** 2 else (1024, 'KB'))
    return f'{size / divisor:.2f} {unit}'


def file_icon(name, *, input_card=False):
    extension = file_extension(name)
    kind = _EXTENSION_KIND.get(extension.lower(), 'unknown')
    layout = 'agent-input-icon' if input_card else 'model-file-icon'
    label = ('<text x="12" y="17.5" text-anchor="middle" stroke="none" fill="currentColor" font-size="' + ('4' if len(extension) >= 4 else '5') + '" font-weight="600"'
             + (' textLength="10" lengthAdjust="spacingAndGlyphs"' if len(extension) >= 4 else '')
             + '>' + html.escape(extension) + '</text>') if extension and len(extension) <= 5 else ''
    # Fixed markup and palette key; no filename is interpolated as HTML or CSS.
    return ('<span class="' + layout + ' agent-file-icon" data-file-kind="' + kind + '" aria-hidden="true">'
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9H13z" fill="currentColor" fill-opacity="0.14"/>'
            '<path d="M13 2l7 7" fill="none"/>' + label + '</svg></span>')
