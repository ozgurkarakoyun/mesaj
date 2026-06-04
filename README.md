# 🔐 PrivateMsg — İki Kişilik Özel Mesajlaşma

Sadece 2 kişi için, özel kod ile giriş yapılan, sesli/görüntülü arama destekli anlık mesajlaşma uygulaması.

## Özellikler

- ✅ Özel kod ile giriş (2 kişi)
- 💬 Anlık mesajlaşma (WebSocket)
- 📸 Fotoğraf / dosya gönderme
- 🎙️ Sesli arama (WebRTC)
- 📹 Görüntülü arama (WebRTC)
- 🟢 Çevrimiçi/çevrimdışı durumu
- ⌨️ "Yazıyor..." göstergesi

---

## Railway'e Deploy Adımları

### 1. GitHub'a Yükle

```bash
git init
git add .
git commit -m "initial commit"
git branch -M main
git remote add origin https://github.com/KULLANICI/privatemsg.git
git push -u origin main
```

### 2. Railway Projesi Oluştur

1. https://railway.app → **New Project**
2. **Deploy from GitHub repo** → Bu repoyu seç
3. Railway otomatik build yapacak

### 3. Environment Variables Ekle (ÖNEMLİ!)

Railway dashboard → Projen → **Variables** sekmesi:

| Değişken | Açıklama | Örnek |
|----------|----------|-------|
| `SECRET_KEY` | Flask secret key (rastgele uzun string) | `kAB92xzT8mQpR...` |
| `USER1_CODE` | 1. kişinin giriş kodu | `OZG-2024` |
| `USER2_CODE` | 2. kişinin giriş kodu | `AYS-2024` |
| `USER1_NAME` | 1. kişinin görünen adı | `Özgür` |
| `USER2_NAME` | 2. kişinin görünen adı | `Ayşe` |

### 4. Domain Al

Railway → Settings → **Generate Domain** → URL kopyala → paylaş

---

## Yerel Test

```bash
pip install -r requirements.txt
python app.py
# → http://localhost:5000
```

Varsayılan kodlar: `KARA-001` ve `KARA-002`

---

## WebRTC / Güvenlik Notları

- Sesli/görüntülü arama için **HTTPS zorunlu** (Railway otomatik sağlar)
- Medya stream'leri peer-to-peer gider, sunucudan geçmez
- Fotoğraflar Railway'in `/static/uploads/` klasörüne kaydedilir
- Deployment sonrası uploads sıfırlanır — kalıcı depolama için Railway Volume ekleyebilirsin

---

## Klasör Yapısı

```
privatemsg/
├── app.py              # Ana Flask uygulaması
├── requirements.txt
├── Procfile
├── railway.json
├── templates/
│   ├── login.html      # Giriş sayfası
│   └── chat.html       # Sohbet + WebRTC
└── static/
    └── uploads/        # Yüklenen dosyalar
```
