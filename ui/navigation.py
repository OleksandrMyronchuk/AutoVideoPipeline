from nicegui import ui

from ui.theme import configure_theme


class NavigationMixin:
    VALID_PAGES = {'cut', 'analyze', 'settings'}

    def build(self, initial_page='cut'):
        initial_page = initial_page if initial_page in self.VALID_PAGES else 'cut'
        self.settings.last_page = initial_page
        self.settings_store.save(self.settings)
        configure_theme()
        with ui.left_drawer(value=True).classes('app-sidebar w-64 p-5'):
            ui.label('AVP').classes('bg-orange-600 text-white text-2xl font-black px-3 py-1 rounded-sm')
            ui.label('AUTO VIDEO\nPIPELINE').classes('text-white text-lg font-semibold mt-4 mb-10 whitespace-pre-line')
            self.nav_button('content_cut', 'Cut Video', 'cut')
            self.nav_button('analytics', 'Analyze Video', 'analyze')
            self.nav_button('settings', 'Settings', 'settings')
            ui.space()
            ui.label('LOCAL PROCESSING').classes('text-slate-500 text-xs font-semibold')

        with ui.column().classes('w-full min-h-screen p-8 md:p-12 app-panel'):
            self.build_cut_page()
            self.build_analyze_page()
            self.build_settings_page()
        self.show_page(initial_page)

    def nav_button(self, icon, label, page):
        route = f'/{page}_video' if page != 'settings' else '/settings'
        ui.button(label, icon=icon, on_click=lambda: self.navigate_to_page(page, route)).props('flat align=left').classes('w-full text-slate-300 justify-start')

    def navigate_to_page(self, page, route):
        if page in self.VALID_PAGES:
            self.settings.last_page = page
            self.settings_store.save(self.settings)
        ui.navigate.to(route)

    def page_header(self, title, subtitle):
        ui.label(title).classes('text-white text-4xl font-semibold')
        ui.label(subtitle).classes('muted mt-1 mb-8')

    def show_page(self, page_name):
        for name, page in self.pages.items():
            page.set_visibility(name == page_name)