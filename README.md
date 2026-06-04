# 🔐 PrivateMsg — İki Kişilik Özel Mesajlaşma

Sadece 2 kişi için, özel kod ile giriş yapılan, WhatsApp benzeri tema, fotoğraf/kamera gönderimi, okundu bilgisi ve sesli/görüntülü arama destekli anlık mesajlaşma uygulaması.

> Not: Uygulama HTTPS altında çalıştığında bağlantı taşıma katmanında korunur. Bu sürüm uçtan uca şifreleme (E2EE) yapmaz; mesajlar sunucu veritabanında düz metin olarak saklanır.

## Özellikler

- ✅ Özel kod ile giriş (2 kişi)
- 🟢 WhatsApp benzeri yeşil sohbet teması
- 💬 Anlık mesajlaşma (WebSocket)
- 🖼️ Galeriden fotoğraf gönderme, önizleme ve sohbet içinde görsel gösterimi
- 📷 Kameradan fotoğraf çekip gönderme
- 📎 PDF / MP4 dosya gönderme
- ✓✓ Mesaj okundu bilgisinde çift tik; okunduğunda mavi çift tik
- 🎙️ Sesli arama (WebRTC)
- 📹 WhatsApp benzeri tam ekran görüntülü arama arayüzü
- 🟢 Çevrimiçi/çevrimdışı durumu
- ⌨️ "Yazıyor..." göstergesi
- 🗄️ PostgreSQL varsa kalıcı kayıt, yoksa yerel SQLite fallback
- 🛡️ Login rate-limit

---

## Fotoğraf ve Kamera Gönderme

Sohbet ekranında üç medya butonu vardır:

- `📷` Kamerayı açar, fotoğraf çeker ve gönderir.
- `🖼️` Galeriden fotoğraf seçer. PNG, JPG, JPEG, GIF ve WEBP desteklenir.
- `📎` Dosya gönderir. PDF ve MP4 desteklenir.

Galeriden fotoğraf seçildiğinde önce küçük bir önizleme görünür. Kullanıcı **Gönder** ile fotoğrafı gönderir veya **İptal** ile seçimi temizler.

Kamera özelliği tarayıcı izni gerektirir. Mobilde arka/ön kamera geçişi için **Çevir** butonu eklenmiştir.

Backend tarafında fotoğraflar özel olarak `/upload/photo` endpoint'i ile yüklenir. Yüklenen görseller sohbet içinde doğrudan görüntülenir ve tıklanınca büyütülür.

---

## Okundu Bilgisi

Mesajlar karşı tarafın sohbet ekranına yüklendiğinde veya sohbet ekranı aktifken görüldüğünde `messages_read` Socket.IO eventi ile sunucuya bildirilir.

- Gri `✓✓`: mesaj gönderildi, henüz okundu bilgisi yok.
- Mavi `✓✓`: karşı taraf mesajı okudu.

Okundu bilgisi veritabanında `read_at` alanında saklanır.

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

### 3. PostgreSQL Ekle

Railway dashboard içinde projeye PostgreSQL servisi ekleyin. Railway `DATABASE_URL` değişkenini otomatik verir.

PostgreSQL eklenmezse uygulama SQLite ile çalışır; ancak Railway dosya sistemi kalıcı olmadığı için deploy/restart sonrası SQLite verileri kaybolabilir.

### 4. Environment Variables Ekle (ÖNEMLİ!)

Railway dashboard → Projen → **Variables** sekmesi:

| Değişken | Açıklama | Örnek |
|----------|----------|-------|
| `SECRET_KEY` | Flask secret key. Production'da zorunlu. | `kAB92xzT8mQpR...` |
| `USER1_CODE` | 1. kişinin giriş kodu. Production'da zorunlu. | `OZG-2026` |
| `USER2_CODE` | 2. kişinin giriş kodu. Production'da zorunlu. | `AYS-2026` |
| `USER1_NAME` | 1. kişinin görünen adı | `Özgür` |
| `USER2_NAME` | 2. kişinin görünen adı | `Kişi 2` |
| `APP_TIMEZONE` | Saat dilimi | `Europe/Istanbul` |

Güvenlik için `USER1_CODE` ve `USER2_CODE` uzun, tahmin edilemez ve birbirinden farklı olmalıdır.

### 5. Domain Al

Railway → Settings → **Generate Domain** → URL kopyala → paylaş.

---

## Yerel Test

```bash
pip install -r requirements.txt
python app.py
# → http://localhost:5000
```

Yerel geliştirme için varsayılan kodlar: `KARA-001` ve `KARA-002`.

Production ortamında bu varsayılan kodlar kullanılmaz; `USER1_CODE`, `USER2_CODE` ve `SECRET_KEY` tanımlanmadığında uygulama başlamaz.

---

## WebRTC / Güvenlik Notları

- Sesli/görüntülü arama için **HTTPS zorunlu**. Railway otomatik HTTPS sağlar.
- Medya stream'leri WebRTC ile peer-to-peer gitmeye çalışır.
- Kodda STUN sunucuları vardır. Bazı mobil ağlar, kurumsal ağlar veya sıkı NAT ortamlarında arama için TURN sunucusu gerekebilir.
- Fotoğraflar Railway'in `/static/uploads/` klasörüne kaydedilir.
- Railway dosya sistemi kalıcı değildir. Kalıcı dosya saklama için Railway Volume veya harici obje depolama gerekir.
- Mesajlar E2EE değildir. Sunucu/veritabanı mesaj içeriğine erişebilir.

---

## Klasör Yapısı

```text
privatemsg/
├── app.py              # Ana Flask uygulaması
├── requirements.txt
├── Procfile
├── railway.json
├── templates/
│   ├── login.html      # Giriş sayfası
│   └── chat.html       # Sohbet + WebRTC
├── static/
│   └── uploads/        # Yüklenen dosyalar
└── data/               # Yerel SQLite veritabanı (runtime'da oluşur)
```
