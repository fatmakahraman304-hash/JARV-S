"""Sample hologram models (what Gemini returns), for previews and tests."""

MUG = {"name": "Seramik kupa", "summary": "Kulplu, beyaz sırlı seramik kahve kupası; içinde kahve.", "parts": [
    {"name": "Gövde", "shape": "lathe", "size": [8.6, 10, 8.6], "pos": [0, 5, 0], "color": "#f2f0ea", "rough": 0.18,
     "profile": [[0, 0], [0.82, 0], [0.9, 0.02], [0.93, 0.08], [0.95, 0.5], [1, 0.97], [0.97, 1], [0.9, 0.99], [0.9, 0.2], [0, 0.2]]},
    {"name": "Kulp", "shape": "tube", "size": [1.3, 6, 3], "pos": [4.3, 5.4, 0], "color": "#f2f0ea", "rough": 0.18,
     "path": [[-0.3, 2.6, 0], [1.6, 2.7, 0], [2.7, 1.6, 0], [2.9, 0, 0], [2.6, -1.6, 0], [1.4, -2.6, 0], [-0.3, -2.5, 0]]},
    {"name": "Kahve", "shape": "cylinder", "size": [7.6, 0.3, 7.6], "pos": [0, 8.9, 0], "color": "#3b2112", "rough": 0.08},
    {"name": "Taban halkası", "shape": "torus", "size": [7.4, 0.5, 7.4], "pos": [0, 0.2, 0], "color": "#d9d4c8", "rough": 0.6}]}

PHONE = {"name": "Akıllı telefon", "summary": "Alüminyum çerçeveli, cam ön yüzlü akıllı telefon.", "parts": [
    {"name": "Gövde", "shape": "rounded_box", "size": [7.8, 16, 0.8], "pos": [0, 8, 0], "radius": 0.38, "color": "#2e3136", "metal": 1, "rough": 0.3},
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
    {"name": "Kafa bandı", "shape": "tube", "size": [1.6, 18, 3], "pos": [0, 12, 0], "color": "#1d1e22", "rough": 0.55,
     "path": [[-8.2, -6, 0], [-8, -1, 0], [-6.5, 3.5, 0], [-3.5, 6, 0], [0, 6.8, 0], [3.5, 6, 0], [6.5, 3.5, 0], [8, -1, 0], [8.2, -6, 0]]},
    {"name": "Sol kulaklık", "shape": "lathe", "size": [7.5, 3, 7.5], "pos": [-8.6, 5.5, 0], "rot": [0, 0, 90], "color": "#2a2b30", "rough": 0.35, "metal": 0.2,
     "profile": [[0, 0], [0.85, 0], [1, 0.25], [1, 0.75], [0.9, 1], [0, 1]]},
    {"name": "Sağ kulaklık", "shape": "lathe", "size": [7.5, 3, 7.5], "pos": [8.6, 5.5, 0], "rot": [0, 0, 90], "color": "#2a2b30", "rough": 0.35, "metal": 0.2,
     "profile": [[0, 0], [0.85, 0], [1, 0.25], [1, 0.75], [0.9, 1], [0, 1]]},
    {"name": "Sol yastık", "shape": "torus", "size": [7.2, 2.4, 7.2], "pos": [-7, 5.5, 0], "rot": [0, 0, 90], "color": "#111214", "rough": 0.8},
    {"name": "Sağ yastık", "shape": "torus", "size": [7.2, 2.4, 7.2], "pos": [7, 5.5, 0], "rot": [0, 0, 90], "color": "#111214", "rough": 0.8},
    {"name": "Sol halka", "shape": "torus", "size": [7.7, 0.4, 7.7], "pos": [-10.05, 5.5, 0], "rot": [0, 0, 90], "color": "#b8bcc4", "metal": 1, "rough": 0.15},
    {"name": "Sağ halka", "shape": "torus", "size": [7.7, 0.4, 7.7], "pos": [10.05, 5.5, 0], "rot": [0, 0, 90], "color": "#b8bcc4", "metal": 1, "rough": 0.15},
    {"name": "Durum ışığı", "shape": "sphere", "size": [0.35, 0.35, 0.35], "pos": [10.2, 4, 1.8], "color": "#5ef0a8", "emissive": 1}]}

HELMET = {"name": "Iron Man kaskı", "summary": "Kırmızı-altın Mark serisi kask.", "parts": [
    {"name": "Kafatası", "shape": "sphere", "size": [21, 25, 23], "pos": [0, 13.5, -1], "color": "#9e1418", "metal": 1, "rough": 0.22},
    {"name": "Yüz plakası", "shape": "extrude", "size": [15, 17, 3], "pos": [0, 11.5, 10], "color": "#d4a52c", "metal": 1, "rough": 0.2, "bevel": 0.4,
     "outline": [[-1, 0.85], [-0.55, 1], [0.55, 1], [1, 0.85], [0.95, 0.1], [0.7, -0.55], [0.35, -0.95], [-0.35, -0.95], [-0.7, -0.55], [-0.95, 0.1]]},
    {"name": "Sol göz", "shape": "extrude", "size": [4.2, 1.2, 0.4], "pos": [-3.4, 14.5, 11.6], "rot": [0, -12, 0], "color": "#dff6ff", "emissive": 1,
     "outline": [[-1, 0.3], [1, 1], [0.85, -1], [-1, -0.6]]},
    {"name": "Sağ göz", "shape": "extrude", "size": [4.2, 1.2, 0.4], "pos": [3.4, 14.5, 11.6], "rot": [0, 12, 0], "color": "#dff6ff", "emissive": 1,
     "outline": [[1, 0.3], [-1, 1], [-0.85, -1], [1, -0.6]]},
    {"name": "Çene", "shape": "rounded_box", "size": [12, 4, 6], "pos": [0, 3.5, 7], "radius": 1.5, "color": "#9e1418", "metal": 1, "rough": 0.22},
    {"name": "Boyun halkası", "shape": "torus", "size": [19, 3, 19], "pos": [0, 1.2, -1], "color": "#3a3a3e", "metal": 1, "rough": 0.35}]}

ALL = [MUG, PHONE, HEADPHONES, HELMET]
