"""Sample hologram models (what Gemini returns), for previews and tests."""

MUG = {"name": "Seramik kupa", "summary": "Kulplu, beyaz sırlı seramik kahve kupası; içinde kahve.", "parts": [
    {"name": "Gövde", "shape": "lathe", "size": [8.6, 10, 8.6], "pos": [0, 5, 0], "color": "#f2f0ea", "rough": 0.18,
     "profile": [[0, 0], [0.82, 0], [0.9, 0.02], [0.93, 0.08], [0.95, 0.5], [1, 0.97], [0.97, 1], [0.9, 0.99], [0.9, 0.2], [0, 0.2]]},
    {"name": "Kulp", "shape": "tube", "size": [1.3, 6, 3], "pos": [4.3, 5.4, 0], "color": "#f2f0ea", "rough": 0.18,
     "path": [[-0.3, 2.6, 0], [1.6, 2.7, 0], [2.7, 1.6, 0], [2.9, 0, 0], [2.6, -1.6, 0], [1.4, -2.6, 0], [-0.3, -2.5, 0]]},
    {"name": "Kahve", "shape": "cylinder", "size": [7.6, 0.3, 7.6], "pos": [0, 8.9, 0], "color": "#3b2112", "rough": 0.08},
    {"name": "Taban halkası", "shape": "torus", "size": [7.4, 0.5, 7.4], "pos": [0, 0.2, 0], "color": "#d9d4c8", "rough": 0.6}]}

PHONE = {"name": "Akıllı telefon", "summary": "Alüminyum çerçeveli, cam ön yüzlü akıllı telefon.", "parts": [
    {"name": "Gövde", "shape": "rounded_box", "size": [7.8, 16, 0.8], "pos": [0, 8, 0], "radius": 0.38, "color": "#8d9096", "metal": 1, "rough": 0.32, "finish": "brushed"},
    {"name": "Ekran", "shape": "rounded_box", "size": [7.3, 15.5, 0.06], "pos": [0, 8, 0.41], "radius": 0.03, "color": "#1b4f8a", "emissive": 0.55, "rough": 0.05},
    {"name": "Dinamik ada", "shape": "capsule", "size": [0.4, 1.9, 0.05], "pos": [0, 15.2, 0.45], "rot": [0, 0, 90], "color": "#050505", "rough": 0.2},
    {"name": "Kamera adası", "shape": "rounded_box", "size": [3.6, 3.7, 0.25], "pos": [-1.7, 13.6, -0.5], "radius": 0.6, "color": "#3a3d42", "metal": 0.6, "rough": 0.25},
    {"name": "Lens 1", "shape": "cylinder", "size": [1.4, 0.35, 1.4], "pos": [-2.5, 14.5, -0.72], "rot": [90, 0, 0], "color": "#0b0c10", "rough": 0.05, "metal": 0.4},
    {"name": "Lens 2", "shape": "cylinder", "size": [1.4, 0.35, 1.4], "pos": [-2.5, 12.7, -0.72], "rot": [90, 0, 0], "color": "#0b0c10", "rough": 0.05, "metal": 0.4},
    {"name": "Lens 3", "shape": "cylinder", "size": [1.4, 0.35, 1.4], "pos": [-0.9, 13.6, -0.72], "rot": [90, 0, 0], "color": "#0b0c10", "rough": 0.05, "metal": 0.4},
    {"name": "Flaş", "shape": "cylinder", "size": [0.5, 0.2, 0.5], "pos": [-0.9, 14.9, -0.68], "rot": [90, 0, 0], "color": "#fff3d0", "emissive": 0.3},
    {"name": "Ses tuşu +", "shape": "capsule", "size": [0.25, 1.4, 0.3], "pos": [-3.95, 12, 0], "color": "#2e3136", "metal": 1, "rough": 0.3},
    {"name": "Ses tuşu −", "shape": "capsule", "size": [0.25, 1.4, 0.3], "pos": [-3.95, 10.2, 0], "color": "#2e3136", "metal": 1, "rough": 0.3},
    {"name": "Güç tuşu", "shape": "capsule", "size": [0.25, 2.2, 0.3], "pos": [3.95, 11, 0], "color": "#2e3136", "metal": 1, "rough": 0.3}]}

HEADPHONES = {"name": "Kulaklık", "summary": "Kulak üstü kablosuz kulaklık, deri yastıklı.", "parts": [
    {"name": "Kafa bandı", "shape": "tube", "size": [1.6, 18, 3], "pos": [0, 12, 0], "color": "#1d1e22", "rough": 0.55, "finish": "leather",
     "path": [[-8.2, -6, 0], [-8, -1, 0], [-6.5, 3.5, 0], [-3.5, 6, 0], [0, 6.8, 0], [3.5, 6, 0], [6.5, 3.5, 0], [8, -1, 0], [8.2, -6, 0]]},
    {"name": "Sol kulaklık", "shape": "lathe", "size": [7.5, 3, 7.5], "pos": [-8.6, 5.5, 0], "rot": [0, 0, 90], "color": "#2a2b30", "rough": 0.35, "metal": 0.2,
     "profile": [[0, 0], [0.85, 0], [1, 0.25], [1, 0.75], [0.9, 1], [0, 1]]},
    {"name": "Sağ kulaklık", "shape": "lathe", "size": [7.5, 3, 7.5], "pos": [8.6, 5.5, 0], "rot": [0, 0, 90], "color": "#2a2b30", "rough": 0.35, "metal": 0.2,
     "profile": [[0, 0], [0.85, 0], [1, 0.25], [1, 0.75], [0.9, 1], [0, 1]]},
    {"name": "Sol yastık", "shape": "torus", "size": [7.2, 2.4, 7.2], "pos": [-7, 5.5, 0], "rot": [0, 0, 90], "color": "#111214", "rough": 0.8, "finish": "leather"},
    {"name": "Sağ yastık", "shape": "torus", "size": [7.2, 2.4, 7.2], "pos": [7, 5.5, 0], "rot": [0, 0, 90], "color": "#111214", "rough": 0.8, "finish": "leather"},
    {"name": "Sol halka", "shape": "torus", "size": [7.7, 0.4, 7.7], "pos": [-10.05, 5.5, 0], "rot": [0, 0, 90], "color": "#b8bcc4", "metal": 1, "rough": 0.15},
    {"name": "Sağ halka", "shape": "torus", "size": [7.7, 0.4, 7.7], "pos": [10.05, 5.5, 0], "rot": [0, 0, 90], "color": "#b8bcc4", "metal": 1, "rough": 0.15},
    {"name": "Durum ışığı", "shape": "sphere", "size": [0.35, 0.35, 0.35], "pos": [10.2, 4, 1.8], "color": "#5ef0a8", "emissive": 1}]}

HELMET = {"name": "Iron Man kaskı", "summary": "Kırmızı-altın Mark serisi kask; parlak metal kaplama, ışıklı gözler.", "parts": [
    {"name": "Kafatası", "shape": "loft", "size": [22, 27, 26], "pos": [0, 13.5, -0.5], "color": "#a3161b", "metal": 0.3, "rough": 0.3, "finish": "paint", "round": 2.3,
     "sections": [[0, .74, .78, 0, .04], [.15, .9, .95, 0, .02], [.45, 1, 1, 0, 0], [.72, .94, .92, 0, -.03], [.9, .7, .7, 0, -.06], [1, .12, .14, 0, -.06]]},
    {"name": "Yüz plakası", "shape": "loft", "size": [16.5, 19, 7], "pos": [0, 11, 10.2], "color": "#d6a634", "metal": 1, "rough": 0.16, "round": 3.2,
     "sections": [[0, .42, .55, 0, -.1], [.18, .72, .8, 0, .05], [.5, .98, 1, 0, 0], [.8, 1, .85, 0, -.15], [1, .86, .45, 0, -.45]]},
    {"name": "Sol göz", "shape": "rounded_box", "size": [4.2, 1.1, 0.6], "pos": [-3.3, 14.6, 13.4], "rot": [0, -14, -6], "radius": 0.25, "color": "#e6f8ff", "emissive": 1},
    {"name": "Sağ göz", "shape": "rounded_box", "size": [4.2, 1.1, 0.6], "pos": [3.3, 14.6, 13.4], "rot": [0, 14, 6], "radius": 0.25, "color": "#e6f8ff", "emissive": 1},
    {"name": "Ağız yarığı", "shape": "rounded_box", "size": [5, 0.35, 0.6], "pos": [0, 6.4, 13.2], "radius": 0.15, "color": "#1a1a1a", "rough": 0.6},
    {"name": "Çene", "shape": "loft", "size": [14, 6, 10], "pos": [0, 3.2, 6], "color": "#a3161b", "metal": 1, "rough": 0.18, "round": 2.6,
     "sections": [[0, .55, .6, 0, .2], [.5, .9, .9, 0, .05], [1, 1, 1, 0, 0]]},
    {"name": "Kulak plakası sol", "shape": "cylinder", "size": [5, 1.2, 5], "pos": [-11.1, 12, -1], "rot": [0, 0, 90], "color": "#c9952c", "metal": 1, "rough": 0.2},
    {"name": "Kulak plakası sağ", "shape": "cylinder", "size": [5, 1.2, 5], "pos": [11.1, 12, -1], "rot": [0, 0, 90], "color": "#c9952c", "metal": 1, "rough": 0.2},
    {"name": "Boyun halkası", "shape": "torus", "size": [18, 2.6, 18], "pos": [0, 1.2, -1], "color": "#3a3a3e", "metal": 1, "rough": 0.3}]}

MOUSE = {"name": "Kablosuz fare", "summary": "Ergonomik, mat siyah kablosuz bilgisayar faresi.", "parts": [
    {"name": "Gövde", "shape": "loft", "size": [6.6, 4, 11.5], "pos": [0, 2, 0], "rot": [0, 0, 0], "color": "#202226", "rough": 0.7, "finish": "matte", "round": 2.6,
     "sections": [[0, .92, .95, 0, 0], [.35, 1, 1, 0, 0], [.7, .86, .9, 0, -.05], [.92, .55, .65, 0, -.1], [1, .2, .3, 0, -.12]]},
    {"name": "Kaydırma tekerleği", "shape": "cylinder", "size": [1.2, 0.5, 1.2], "pos": [0, 3.75, 2.6], "rot": [0, 0, 90], "color": "#5a5d63", "metal": 0.6, "rough": 0.35},
    {"name": "Durum ışığı", "shape": "sphere", "size": [0.25, 0.1, 0.25], "pos": [0, 3.55, 1.2], "color": "#5ef0a8", "emissive": 1}]}

KEYBOARD = {"name": "Mekanik klavye", "summary": "Alüminyum kasalı, 60% mekanik klavye.", "parts": [
    {"name": "Kasa", "shape": "rounded_box", "size": [29.5, 3, 10.5], "pos": [0, 1.5, 0], "radius": 0.5, "color": "#9da2a8", "metal": 1, "rough": 0.35, "finish": "brushed"},
    {"name": "Plaka", "shape": "box", "size": [28.6, 0.3, 9.6], "pos": [0, 3.05, 0], "color": "#1b1c1f", "metal": 1, "rough": 0.4},
    {"name": "Tuş sırası 1", "shape": "rounded_box", "size": [1.75, 1.0, 1.75], "pos": [-12.4, 3.6, -3.8], "radius": 0.25, "color": "#e8e4dc", "rough": 0.55, "finish": "matte",
     "array": {"count": 14, "step": [1.905, 0, 0]}},
    {"name": "Tuş sırası 2", "shape": "rounded_box", "size": [1.75, 1.0, 1.75], "pos": [-11.5, 3.6, -1.9], "radius": 0.25, "color": "#e8e4dc", "rough": 0.55, "finish": "matte",
     "array": {"count": 13, "step": [1.905, 0, 0]}},
    {"name": "Tuş sırası 3", "shape": "rounded_box", "size": [1.75, 1.0, 1.75], "pos": [-11.0, 3.6, 0.0], "radius": 0.25, "color": "#e8e4dc", "rough": 0.55, "finish": "matte",
     "array": {"count": 12, "step": [1.905, 0, 0]}},
    {"name": "Tuş sırası 4", "shape": "rounded_box", "size": [1.75, 1.0, 1.75], "pos": [-10.0, 3.6, 1.9], "radius": 0.25, "color": "#e8e4dc", "rough": 0.55, "finish": "matte",
     "array": {"count": 11, "step": [1.905, 0, 0]}},
    {"name": "Boşluk tuşu", "shape": "rounded_box", "size": [11.8, 1.0, 1.75], "pos": [0, 3.6, 3.8], "radius": 0.25, "color": "#d05a2a", "rough": 0.5, "finish": "matte"},
    {"name": "Escape", "shape": "rounded_box", "size": [1.75, 1.0, 1.75], "pos": [-12.4, 3.6, 3.8], "radius": 0.25, "color": "#d05a2a", "rough": 0.5, "mirror": "x"},
    {"name": "Lastik ayak", "shape": "cylinder", "size": [1.2, 0.3, 1.2], "pos": [12.5, 0.1, 4], "color": "#111111", "rough": 0.9, "finish": "rubber", "mirror": "xz"},
    {"name": "USB-C", "shape": "rounded_box", "size": [0.9, 0.35, 0.4], "pos": [-11, 1.6, -5.3], "radius": 0.15, "color": "#222222", "metal": 1, "rough": 0.3}]}

WHEEL = {"name": "Spor jant", "summary": "Beş çift kollu, parlak işlenmiş alüminyum jant ve lastik.", "parts": [
    {"name": "Lastik", "shape": "lathe", "size": [64, 22, 64], "pos": [0, 32, 0], "rot": [90, 0, 0], "color": "#151515", "rough": 0.85, "finish": "rubber",
     "profile": [[0.72, 0], [0.9, 0.02], [0.985, 0.14], [1, 0.5], [0.985, 0.86], [0.9, 0.98], [0.72, 1]]},
    {"name": "Diş", "shape": "rounded_box", "size": [3, 1.4, 19], "pos": [0, 63.7, 0], "radius": 0.4, "color": "#101010", "rough": 0.9, "finish": "rubber",
     "radial": {"count": 48, "axis": "z", "center": [0, 32, 0]}},
    {"name": "Jant çemberi", "shape": "lathe", "size": [47, 20, 47], "pos": [0, 32, 0], "rot": [90, 0, 0], "color": "#b9bcc2", "metal": 1, "rough": 0.2, "finish": "brushed",
     "profile": [[0.92, 0], [1, 0.05], [0.93, 0.15], [0.93, 0.85], [1, 0.95], [0.92, 1]]},
    {"name": "Göbek", "shape": "lathe", "size": [14, 6, 14], "pos": [0, 32, 7], "rot": [90, 0, 0], "color": "#2b2d31", "metal": 1, "rough": 0.3,
     "profile": [[0, 0], [1, 0], [0.95, 0.6], [0.6, 1], [0, 1]]},
    {"name": "Kol", "shape": "extrude", "size": [3.2, 16, 2.4], "pos": [0, 44, 6], "rot": [0, 0, 0], "color": "#c9ccd2", "metal": 1, "rough": 0.18,
     "outline": [[-0.6, -1], [0.6, -1], [1, 1], [-1, 1]], "radial": {"count": 10, "axis": "z", "center": [0, 32, 6]}},
    {"name": "Bijon", "shape": "cylinder", "size": [1.4, 1.2, 1.4], "pos": [0, 35, 9.8], "rot": [90, 0, 0], "color": "#d4d6da", "metal": 1, "rough": 0.15, "finish": "knurl",
     "radial": {"count": 5, "axis": "z", "center": [0, 32, 9.8]}},
    {"name": "Fren diski", "shape": "cylinder", "size": [34, 2.6, 34], "pos": [0, 32, -3], "rot": [90, 0, 0], "color": "#6b6e72", "metal": 1, "rough": 0.45, "finish": "brushed"},
    {"name": "Kaliper", "shape": "rounded_box", "size": [8, 14, 5], "pos": [13, 38, -3], "rot": [0, 0, -30], "radius": 1.5, "color": "#c8102e", "metal": 0.2, "rough": 0.25, "finish": "paint"}]}

ALL = [MUG, PHONE, HEADPHONES, HELMET, MOUSE, KEYBOARD, WHEEL]
