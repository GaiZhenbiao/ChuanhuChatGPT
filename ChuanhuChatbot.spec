# -*- mode: python ; coding: utf-8 -*-


block_cipher = None


a = Analysis(
    ['ChuanhuChatbot.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('custom.css','.'),
        ('templates/1 中文Prompts.json','templates'),
        ('templates/2 English Prompts.csv','templates'),
        ('templates/3 川虎的Prompts.json','templates')
    ],
    hiddenimports=[],
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ChuanhuChatbot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['res\\226267132-e5295925-f53a-4e9d-a221-6099583da98d.ico'],
)
