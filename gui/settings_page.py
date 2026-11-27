"""Categorised settings with accessible, draggable switches."""
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (QAbstractButton, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QPlainTextEdit, QFormLayout, QScrollArea, QWidget, QStackedWidget, QFrame)
from gui.theme import C
from gui.style import px_font


class Toggle(QAbstractButton):
    def __init__(self, title):
        super().__init__()
        self.setCheckable(True)
        self.setFixedSize(54, 30)
        self.setAccessibleName(title)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start = None

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C.PRI if self.isChecked() else C.BORDER))
        p.drawRoundedRect(QRectF(1, 2, 52, 26), 13, 13)
        p.setBrush(QColor(C.BG if self.isChecked() else C.WHITE))
        p.drawEllipse(QRectF(29 if self.isChecked() else 5, 6, 18, 18))
        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QColor(C.WHITE))
            p.drawRoundedRect(QRectF(0.5, .5, 53, 29), 14, 14)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = event.position().x()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._start is not None and abs(event.position().x() - self._start) > 5:
            self.setDown(False)
            self.setChecked(event.position().x() > self._start)
            self.clicked.emit(self.isChecked())
        else:
            super().mouseReleaseEvent(event)
        self._start = None


class SettingsPage(QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        from memory import config_manager as cfg
        self.setWindowTitle('FRIDAY — Ayarlar')
        available = self.screen().availableGeometry()
        self.resize(min(980, available.width()-80), min(650, available.height()-100))
        self.setFont(px_font(13))
        self.setStyleSheet(f'''
            QDialog {{ background: {C.BG}; }}
            QLineEdit, QPlainTextEdit {{ background: {C.PANEL}; color: {C.TEXT}; border: 1px solid {C.BORDER}; padding: 8px; }}
            QCheckBox {{ color: {C.TEXT}; }}
            QLabel {{ color: {C.TEXT}; background: transparent; }}
            QWidget#page, QWidget#body {{ background: {C.BG}; }}
            QFrame#card {{ background: {C.PANEL}; border: 1px solid {C.BORDER}; border-radius: 12px; }}
            QFrame#nav {{ background: {C.PANEL}; border-radius: 14px; }}
            QPushButton {{ color: {C.TEXT}; background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 8px; padding: 9px 14px; }}
            QPushButton:hover {{ border-color: {C.PRI}; color: {C.WHITE}; }}
            QPushButton#category {{ text-align: left; border: none; background: transparent; padding: 13px; }}
            QPushButton#category:checked {{ background: {C.PRI_GHO}; color: {C.PRI}; }}
            QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{ background: transparent; width: 6px; margin: 2px; }}
            QScrollBar::handle:vertical {{ background: {C.BORDER_B}; border-radius: 3px; min-height: 25px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        ''')
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 20)
        root.setSpacing(22)
        top = QHBoxLayout()
        heading = QVBoxLayout()
        brand = QLabel('FRIDAY  /  KONTROL MERKEZİ')
        brand.setFont(px_font(10, spacing=2))
        brand.setStyleSheet(f'color: {C.PRI};')
        heading.addWidget(brand)
        title = QLabel('Ayarlar')
        title.setFont(px_font(30))
        heading.addWidget(title)
        top.addLayout(heading)
        top.addStretch()
        close = QPushButton('Kapat  ×')
        close.clicked.connect(self.close)
        top.addWidget(close, alignment=Qt.AlignmentFlag.AlignTop)
        root.addLayout(top)
        content = QHBoxLayout()
        content.setSpacing(24)
        nav = QFrame()
        nav.setObjectName('nav')
        nav.setFixedWidth(190)
        navigation = QVBoxLayout(nav)
        navigation.setContentsMargins(10, 16, 10, 16)
        navigation.setSpacing(6)
        content.addWidget(nav)
        self.stack = QStackedWidget()
        content.addWidget(self.stack, 1)
        root.addLayout(content, 1)
        note = QLabel('Değişiklikler anında uygulanır.  •  Sürgü sağda: açık, solda: kapalı')
        note.setFont(px_font(11))
        note.setStyleSheet(f'color: {C.TEXT_DIM};')
        root.addWidget(note)
        self.syncs, self.categories = [], []
        def page(name, subtitle):
            index = self.stack.count()
            button = QPushButton(name)
            button.setObjectName('category')
            button.setCheckable(True)
            self.categories.append(button)
            navigation.addWidget(button)
            def select():
                self.stack.setCurrentIndex(index)
                for b in self.categories:
                    b.setChecked(b is button)
            button.clicked.connect(select)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            body = QWidget()
            body.setObjectName('body')
            rows = QVBoxLayout(body)
            rows.setContentsMargins(0, 0, 8, 0)
            rows.setSpacing(12)
            label = QLabel(name)
            label.setFont(px_font(22))
            rows.addWidget(label)
            sub = QLabel(subtitle)
            sub.setWordWrap(True)
            sub.setStyleSheet(f'color: {C.TEXT_DIM}; margin-bottom: 8px;')
            rows.addWidget(sub)
            rows.addStretch()
            scroll.setWidget(body)
            self.stack.addWidget(scroll)
            return rows
        def card(rows, title, detail):
            frame = QFrame()
            frame.setObjectName('card')
            row = QHBoxLayout(frame)
            row.setContentsMargins(18, 17, 18, 17)
            row.setSpacing(18)
            text = QVBoxLayout()
            text.setSpacing(6)
            title_lbl = QLabel(title)
            title_lbl.setFont(px_font(14))
            text.addWidget(title_lbl)
            description = QLabel(detail)
            description.setWordWrap(True)
            description.setFont(px_font(11))
            description.setStyleSheet(f'color: {C.TEXT_DIM};')
            text.addWidget(description)
            row.addLayout(text, 1)
            rows.insertWidget(rows.count()-1, frame)
            return row
        def switch(rows, title, detail, getter, action, feedback=None):
            row = card(rows, title, detail)
            control = Toggle(title)
            state = QLabel()
            state.setFont(px_font(10))
            state.setMinimumWidth(38)
            row.addWidget(state)
            row.addWidget(control)
            def sync():
                if control.isDown():
                    return
                value = bool(getter())
                control.setChecked(value)
                busy, message = feedback() if feedback else (False, "")
                # A missing or not-yet-initialised feedback field must not make
                # settings crash while the wake-word controls are being built.
                busy = busy if isinstance(busy, bool) else False
                message = message if isinstance(message, str) else ""
                control.setEnabled(not busy)
                state.setWordWrap(bool(message))
                state.setText(message or ('Açık' if value else 'Kapalı'))
                state.setStyleSheet(f'color: {C.PRI if value else C.TEXT_DIM};')
            def change(value):
                if bool(value) != bool(getter()):
                    action()
                sync()
            control.clicked.connect(change)
            self.syncs.append(sync)
            sync()
        def action(rows, title, detail, callback):
            button = QPushButton('Aç  →')
            button.setAccessibleName(title)
            def open_panel():
                self.hide()
                callback()
            button.clicked.connect(open_panel)
            card(rows, title, detail).addWidget(button)
        general = page('Genel', 'Başlangıç ve günlük kullanım tercihlerin.')
        update_row = card(general, 'FRIDAY güncellemesi', 'GitHub’daki yeni sürümü kontrol et ve yükle.')
        update_row.addWidget(owner._build_update_button())
        switch(general, 'Windows ile başlat', 'Bilgisayar açıldığında FRIDAY hazır olsun.', owner._check_autostart, owner._toggle_autostart)
        switch(general, 'Günlük özet', 'Günlük bilgilendirme rutinini etkinleştir.', cfg.get_brief_enabled, owner._toggle_brief)
        action(general, 'Masaüstü kısayolu', 'FRIDAY’a masaüstünden hızlı eriş.', owner._create_desktop_shortcut)
        voice = page('Ses ve mikrofon', 'Dinleme şeklini ve ses cihazlarını yönet.')
        switch(voice, 'Uyandırma kelimesi', '“Hey FRIDAY” diyerek uyandır. İlk kullanımda çevrimdışı ses modeli indirilir.', lambda: owner._wake_state().get('enabled', False), owner._toggle_wake_word,
               feedback=lambda: (owner._wake_busy, owner._wake_feedback))
        switch(voice, 'Basılı tutarak konuş', 'Yalnızca konuşma tuşunu basılı tutarken dinle.', cfg.get_push_to_talk_enabled, owner._toggle_ptt)
        action(voice, 'Ses cihazları', 'Mikrofon ve hoparlör seçimini değiştir.', owner._open_audio_devices)
        action(voice, 'Uyut / uyandır', 'Geçerli dinleme durumunu değiştir.', owner._tap_wake_manual)
        look = page('Görünüm', 'FRIDAY’ın görünümünü kendine göre düzenle.')
        switch(look, 'Tam ekran', 'Arayüzü ekranın tamamında göster.', owner.isFullScreen, owner._toggle_fullscreen)
        action(look, 'Merkez görünümü', 'CORE ile animasyonlu yüz arasında geçiş yap.', owner._toggle_hud_style)
        brain = page('Zekâ ve hafıza', 'Modellerini ve asistanın hatırladıklarını yönet.')
        action(brain, 'Motor ve sağlayıcılar', 'Yapay zekâ modelleri ve bağlantı ayarları.', owner._open_providers)
        action(brain, 'Hafıza', 'Kaydedilmiş bilgileri görüntüle ve düzenle.', owner._open_memory_panel)
        switch(brain, 'Yerel teşhis ölçümlerini modelle paylaş',
               'Varsayılan kapalıdır. Açılırsa CPU, RAM, disk ve pilin sınırlı ölçümleri '
               'yapılandırılan model sağlayıcısına gönderilebilir; donanım kimlikleri ve ağ adları gönderilmez. '
               'Teşhis, sistem durumu ve uyarılar yerel panelde kalır. Açıkken modele genel bir '
               'uyarı da gönderilebilir. Bu ayar diğer veri ve cihaz eşitleme yollarını kapsamaz.',
               cfg.get_hardware_model_sharing,
               lambda: cfg.save_hardware_model_sharing(not cfg.get_hardware_model_sharing()))
        switch(brain, 'Görev sonucunu modelle incele',
               'Varsayılan kapalıdır. Açıldığında istenen ayrı inceleme, seçili görevin metnini ve '
               'sonucunu yapılandırılan veya yedek model sağlayıcısına gönderebilir; özel bilgiler '
               'içerebilir. Özel hafıza ve donanım araçlarını kullanan görevler bu incelemede engellenir.',
               cfg.get_cognitive_review_sharing,
               lambda: cfg.save_cognitive_review_sharing(not cfg.get_cognitive_review_sharing()))
        app_page = page('Uygulamalar', 'Uygulama adını yaz: kaynakları araştır, eksik kontrolleri geliştir ve test et.')
        app_name = QLineEdit()
        app_name.setPlaceholderText('Örneğin: CapCut, WhatsApp')
        app_name.setAccessibleName('Uygulama adı')
        app_name.setMaxLength(100)
        app_page.insertWidget(app_page.count()-1, app_name)
        app_goal = QLineEdit()
        app_goal.setPlaceholderText('İstenen işlemler (boş bırakırsan mevcut özellikleri araştırır)')
        app_goal.setAccessibleName('İstenen uygulama işlemleri')
        app_goal.setMaxLength(4000)
        app_page.insertWidget(app_page.count()-1, app_goal)
        auto_publish = QCheckBox('Testler ve GitHub kontrolleri geçerse main’e al ve güncelle')
        auto_publish.setChecked(True)
        app_page.insertWidget(app_page.count()-1, auto_publish)
        app_state = QLabel('Kod testleri, uygulamadaki tüm işlemlerin çalıştığı anlamına gelmez. Sonuçlar ayrı doğrulanır.')
        app_state.setWordWrap(True)
        app_page.insertWidget(app_page.count()-1, app_state)
        app_results = QPlainTextEdit()
        app_results.setReadOnly(True)
        app_results.setAccessibleName('Uygulama geliştirme sonuçları')
        app_results.setMinimumHeight(160)
        app_page.insertWidget(app_page.count()-1, app_results)
        def refresh_apps():
            from core.application_learning import report
            try:
                content = report()
                if app_results.toPlainText() != content:
                    app_results.setPlainText(content)
            except Exception as exc:
                app_state.setText(f'Kayıt okunamadı: {exc}')
        def learn_app():
            from plugins.application_learning import run
            # Route output through the existing thread-safe FridayUI bridge.
            player = getattr(owner, '_application_player', None)
            if player is None:
                app_state.setText('FRIDAY başlatılınca tekrar dene.')
                return
            app_state.setText(run({'action': 'learn', 'name': app_name.text(),
                                  'goal': app_goal.text(), 'publish': auto_publish.isChecked()}, player=player))
            refresh_apps()
        learn_btn = QPushButton('Araştır, geliştir ve test et')
        learn_btn.clicked.connect(learn_app)
        app_page.insertWidget(app_page.count()-1, learn_btn)
        self.syncs.append(refresh_apps)
        refresh_apps()
        def show_history():
            from memory.continuity import resume_text
            player = getattr(owner, '_application_player', None)
            if player:
                player.show_content('Nerede kaldık', resume_text())
        action(brain, 'Nerede kaldık', 'Son konuşmalar ve işlem sonuçları; yeniden başlatınca korunur.', show_history)
        extras = page('Bağlantılar', 'Ek yetenekler ve uzaktan erişim.')
        # Composio: 1000+ apps (Gmail, Google Takvim/Drive/Docs/Sheets, Notion…)
        apps_row = card(extras, 'Uygulamalar (Composio)',
                        'Gmail, Google Takvim, Drive, Docs, Sheets, Notion ve 1000+ uygulama. '
                        'composio.dev’de ücretsiz hesap aç, Settings → Sessions & API Key’deki '
                        'ck_ anahtarını (ya da geliştirici panelindeki ak_ anahtarını) buraya yapıştır; '
                        'sonra Kontrol Merkezi’nde gri bir uygulamaya tıklayarak bağla.')
        from core import composio as _composio
        key_edit = QLineEdit()
        key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        key_edit.setPlaceholderText('Composio API anahtarı')
        key_edit.setMinimumWidth(220)
        key_edit.setText(_composio.api_key())
        key_edit.setAccessibleName('Composio API anahtarı')
        apps_row.addWidget(key_edit)
        key_state = QLabel('Kayıtlı' if _composio.is_configured() else '')
        key_state.setFont(px_font(10))
        key_state.setStyleSheet(f'color: {C.PRI};')
        apps_row.addWidget(key_state)
        key_state.setWordWrap(True)
        key_state.setMaximumWidth(260)
        test_result = {}
        def show_result():
            if 'msg' not in test_result:
                QTimer.singleShot(300, show_result)
                return
            ok, msg = test_result.pop('ok'), test_result.pop('msg')
            key_state.setText(('✓ ' if ok else '✕ ') + msg)
            key_state.setToolTip(msg)
            key_state.setStyleSheet(f'color: {C.GREEN if ok else C.RED};')
        def test_key():
            # The network check runs on a worker thread; a timer on the Qt
            # thread picks the answer up, so no widget is touched off-thread.
            key_state.setText('Deneniyor…')
            key_state.setStyleSheet(f'color: {C.TEXT_DIM};')
            import threading
            def work():
                ok, msg = _composio.check()
                test_result['ok'] = ok
                test_result['msg'] = msg
            threading.Thread(target=work, daemon=True, name='composio-check').start()
            QTimer.singleShot(300, show_result)
        def save_key():
            try:
                _composio.save_api_key(key_edit.text())
                key_edit.setText(_composio.api_key())
                if _composio.is_configured():
                    test_key()
                else:
                    key_state.setText('Silindi')
            except Exception as exc:
                key_state.setText(f'Kaydedilemedi: {exc}'[:60])
        save_btn = QPushButton('Kaydet')
        save_btn.setAccessibleName('Composio anahtarını kaydet')
        save_btn.clicked.connect(save_key)
        apps_row.addWidget(save_btn)
        test_btn = QPushButton('Test et')
        test_btn.setAccessibleName('Composio anahtarını dene')
        test_btn.clicked.connect(test_key)
        apps_row.addWidget(test_btn)
        get_btn = QPushButton('Anahtar al')
        get_btn.setAccessibleName('Composio sitesini aç')
        def open_composio():
            import webbrowser
            webbrowser.open('https://dashboard.composio.dev')
        get_btn.clicked.connect(open_composio)
        apps_row.addWidget(get_btn)
        # Home Assistant: lights, AC, blinds, locks, sensors (plugins/smart_home.py)
        ha_row = card(extras, 'Akıllı ev (Home Assistant)',
                      'Işıklar, klima, perde, kilit ve sensörler. Home Assistant’ta Profil → Güvenlik → '
                      'Uzun ömürlü erişim jetonu oluştur ve buraya yapıştır. Adresi boş bırakırsan '
                      'homeassistant.local aranır.')
        from plugins import smart_home as _sh
        _ha = _sh._cfg()
        ha_url = QLineEdit(str(_ha.get('url') or ''))
        ha_url.setPlaceholderText('http://homeassistant.local:8123')
        ha_url.setAccessibleName('Home Assistant adresi')
        ha_url.setMinimumWidth(170)
        ha_row.addWidget(ha_url)
        ha_token = QLineEdit(str(_ha.get('token') or ''))
        ha_token.setEchoMode(QLineEdit.EchoMode.Password)
        ha_token.setPlaceholderText('Erişim jetonu')
        ha_token.setAccessibleName('Home Assistant erişim jetonu')
        ha_token.setMinimumWidth(150)
        ha_row.addWidget(ha_token)
        ha_state = QLabel('Bağlı' if _ha.get('token') else '')
        ha_state.setFont(px_font(10))
        ha_state.setWordWrap(True)
        ha_state.setMaximumWidth(220)
        ha_state.setStyleSheet(f'color: {C.PRI};')
        ha_row.addWidget(ha_state)
        ha_result = {}
        def ha_show():
            if 'msg' not in ha_result:
                QTimer.singleShot(300, ha_show)
                return
            ok, msg = ha_result.pop('ok'), ha_result.pop('msg')
            ha_state.setText(('✓ ' if ok else '✕ ') + msg[:120])
            ha_state.setToolTip(msg)
            ha_state.setStyleSheet(f'color: {C.GREEN if ok else C.RED};')
            if ok:
                ha_url.setText(str(_sh._cfg().get('url') or ha_url.text()))
        def ha_connect():
            # network on a worker thread; a Qt timer reads the answer (no widget touched off-thread)
            ha_state.setText('Bağlanılıyor…')
            ha_state.setStyleSheet(f'color: {C.TEXT_DIM};')
            url, token = ha_url.text().strip(), ha_token.text().strip()
            import threading
            def work():
                ok, msg = _sh.connect(url, token)
                ha_result['ok'], ha_result['msg'] = ok, msg
            threading.Thread(target=work, daemon=True, name='ha-connect').start()
            QTimer.singleShot(300, ha_show)
        ha_btn = QPushButton('Bağlan')
        ha_btn.setAccessibleName('Home Assistant’a bağlan')
        ha_btn.clicked.connect(ha_connect)
        ha_row.addWidget(ha_btn)
        action(extras, "Dünya Haritası", "Yer ara, haritayı gez veya rota görüntüle.",
               lambda: owner._show_world_map(True))
        action(extras, 'Eklentiler', 'Kullanılabilir yetenekleri yönet.', owner._open_plugin_manager)
        action(extras, 'Eklenti ayarları', 'Eklentilere özel seçenekleri düzenle.', owner._open_plugin_settings)
        action(extras, 'Uzaktan kontrol', 'Uzaktan erişim seçeneklerini aç.', owner._open_remote)
        navigation.addStretch()
        self.categories[0].setChecked(True)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(700)

    def show_category(self, name):
        """Switch to a category by its title (e.g. 'Bağlantılar')."""
        for button in self.categories:
            if button.text() == name:
                button.click()
                return True
        return False

    def refresh(self):
        if self.isVisible():
            for sync in self.syncs:
                sync()
