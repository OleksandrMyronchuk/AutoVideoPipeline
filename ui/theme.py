from nicegui import ui


def configure_theme() -> None:
    ui.colors(primary='#f97316', secondary='#202d43', accent='#fb923c', dark='#111827')
    ui.add_head_html('''
        <style>
            body { margin: 0; background: #070b14; color: #f8fafc; }
            .app-sidebar { background: #0b1220; }
            .app-panel { background: #182235; }
            .app-input .q-field__control { background: #202d43; border: 1px solid #334155; }
            .app-input .q-field__native, .app-input .q-field__label, .app-input .q-field__input { color: #f8fafc; }
            .app-input .q-field__append { color: #f8fafc; }
            .muted { color: #93a4bd; }
            .q-linear-progress { background: #202d43; }
            .nicegui-card, .q-card { background: #293952 !important; color: #ffffff !important; }
            .nicegui-card .text-slate-300, .q-card .text-slate-300 { color: #e2e8f0 !important; }
            .q-menu, .q-menu .q-virtual-scroll__content {
                background: #182235 !important;
                color: #f8fafc !important;
                border: 1px solid #334155;
            }
            .q-menu .q-item,
            .q-menu .q-item__label,
            .q-menu .q-item__section {
                color: #f8fafc !important;
            }
            .q-menu .q-item--active {
                background: rgba(249, 115, 22, 0.18) !important;
                color: #ffffff !important;
            }
            .q-menu .q-item:hover {
                background: rgba(148, 163, 184, 0.12) !important;
            }
            .editor-layout { background: #0f172a; border-radius: 12px; padding: 12px; }
            .editor-explorer { background: #111c2e; border-radius: 8px; min-width: 220px; resize: horizontal; overflow: auto; }
            .editor-surface { background: #0b1220; border-radius: 8px; min-width: 0; }
            .editor-host { min-width: 0; resize: vertical; overflow: auto; }
            .editor-host > div { height: 100%; width: 100%; }
            .editor-layout .q-separator { background: #263650; }
            .editor-explorer .q-tree { color: #dbe7f5; }
            .editor-explorer .q-tree__label { color: #dbe7f5; }
            .editor-explorer .q-tree__icon { color: #8db4df; }
        </style>
    ''')