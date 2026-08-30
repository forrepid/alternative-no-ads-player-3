# StreamBridge

StreamBridge; Twitch, Kick ve YouTube canlı yayınlarını tek bir yerel HLS oynatıcıda açan
FastAPI uygulamasıdır. HLS manifestlerini güvenli bir alan adı listesi üzerinden proxy'ler
ve işaretlenmiş reklam segmentlerini filtreleyebilir.

## Yerel kurulum

Python 3.11 veya daha yenisini kullanın:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.venv\Scripts\python run.py
```

Oynatıcı: `http://localhost:8080/player/`  
API belgesi: `http://localhost:8080/docs`  
Sağlık kontrolü: `http://localhost:8080/api/system/health`

Windows'ta daha sonraki çalıştırmalar için `start-streambridge.ps1` dosyasını açabilirsiniz.
Tarayıcı eklentisi güvenlik nedeniyle yerel Python sürecini kendi başına başlatamaz; eklentiyi
kullanmadan önce bu servis çalışıyor olmalıdır.

## Docker

```powershell
docker compose up --build
```

Cloudflare bypass yalnızca gerektiğinde açılır:

```powershell
docker compose --profile cf-bypass up --build
```

## Cloudflare Container dağıtımı

Proje, yerel Docker olmadan Cloudflare Workers Builds üzerinden derlenmek üzere
`wrangler.jsonc` ve `cloudflare/worker.mjs` içerir. Cloudflare Dashboard'da
**Workers & Pages → Create application → Connect GitHub** ile
`forrepid/alternative-no-ads-player-3` deposunu seçin; üretim dalı `master`,
deploy komutu `npx wrangler deploy` olmalıdır. Cloudflare Docker image'ını
uzakta derler ve uygulama `https://alternative-no-ads-player-3.mwplay.workers.dev/player/`
adresinden erişilebilir olur.

## Yapılandırma

Tüm seçenekler [.env.example](.env.example) içinde belgelenmiştir. HLS proxy varsayılan
olarak yalnızca bilinen yayın/CDN alan adlarına ve public HTTPS adreslerine erişir.
`HLS_ALLOWED_HOSTS` ayarlanırsa yerleşik liste tamamen bu virgülle ayrılmış listeyle
değiştirilir.

## Test ve kalite

```powershell
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m ruff check app tests
.venv\Scripts\python -m compileall -q app
```

Chrome eklentisinin tek kaynak dizini `extension-chrome/` klasörüdür. Chrome'da
`chrome://extensions` sayfasından “Paketlenmemiş öğe yükle” ile bu klasörü seçin.
Eski Chrome üretim artıkları içerebilen `extension/` dizini kaynak değildir ve Git dışında
tutulur.

Eklenti, platform oynatıcısının yerinde iki yöntem sunar: mevcut `Iframe` modu ve eklentiye
yerel olarak paketlenmiş HLS.js kullanan, sayfadan izole `Shadow panel` modu. Sayfadaki mod
seçimi `chrome.storage` içinde saklanır. Shadow panel kalite seçimi, tam ekran,
picture-in-picture ve platforma dönüş kontrollerini destekler.
Paketlenen sürüm hls.js `v1.6.16` olup lisans metni `extension-chrome/hls.LICENSE.txt`
dosyasında tutulur. Oynatıcı seçiminde beş yöntem vardır:

1. Yerel StreamBridge API + iframe
2. Yerel StreamBridge API + Shadow DOM
3. Sunucusuz standalone resmî platform embed'i
4. `https://multiwebblayer.mwplay.workers.dev/` üzerinde MultiWebPlayer Cloud
5. `com.streambridge.player` native messaging host'u kullanan masaüstü uygulaması

İlk iki yöntem için yerel servis gerekir. Üçüncü ve dördüncü yöntem yalnızca eklentiyle
çalışır. Beşinci yöntem, ayrıca native host kurulmuşsa etkinleşir.

Yerel API health ve stream çözümleme çağrıları eklentinin service worker köprüsünden yapılır.
Köprü kullanılamazsa content script `targetAddressSpace: "local"` ile Chrome Yerel Ağ
Erişimi iznini isteyen doğrudan yönteme düşer. Yerel Shadow HLS istekleri de aynı adres alanı
işaretini kullanır.

## Sınırlamalar

- Twitch ve diğer platformlar erişim/manifest biçimlerini zaman içinde değiştirebilir.
- Twitch/Kick VOD oynatma henüz desteklenmez.
- `aggressive` filtre stratejisi yanlış pozitif üretebilir; varsayılan `scte35` önerilir.
- Servis internete açılmak üzere tasarlanmamıştır. Kimlik doğrulama eklemeden public bir
  adrese bind etmeyin.

Yayınları ve üçüncü taraf servisleri kullanırken ilgili platform koşullarına ve yerel
mevzuata uyun.
