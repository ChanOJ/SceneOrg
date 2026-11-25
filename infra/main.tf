# The whole bunny.net setup of the site: a storage zone holding the files
# (site/, deployed from the Mac by scripts/deploy.py), a pull zone (CDN) in front
# of it and its public hostname. Every value specific to the site comes from site.json.
#
# DNS is not managed here: the hostname is a CNAME to the pull zone system
# hostname (output cdn_hostname) at the registrar (Infomaniak).

locals {
  site = jsondecode(file("${path.module}/../site.json"))
}

resource "bunnynet_storage_zone" "this" {
  name                = local.site.storage_zone
  region              = "DE"
  replication_regions = []
  zone_tier           = "Standard"

  custom_404_file_path = lookup(local.site, "not_found_page", null)
  rewrite_404_to_200   = false

  # Names cannot change on bunny.net: a new name replaces the zone. The new
  # one is created first; site/ must then be deployed to it from the Mac
  # (scripts/publish.sh), since CI cannot build the site.
  lifecycle {
    create_before_destroy = true
  }
}

resource "bunnynet_pullzone" "this" {
  name = local.site.pullzone

  origin {
    type        = "StorageZone"
    storagezone = bunnynet_storage_zone.this.id
  }

  routing {
    tier  = "Standard"
    zones = ["EU"]
  }

  cors_enabled    = true
  cors_extensions = ["css", "eot", "gif", "jpeg", "jpg", "js", "json", "mp3", "mp4", "mpeg", "png", "svg", "ttf", "webm", "webp", "woff", "woff2"]

  # Read-only site: no POST at all (also refused by the edge rule below), and
  # no cookies ever reach the origin.
  block_post_requests = true
  strip_cookies       = true

  block_no_referer = true
  cache_chunked    = true
  log_anonymized   = true

  # CDN cache: 30 days (purged by scripts/deploy.py on each deployment);
  # browsers: as told by the origin.
  cache_expiration_time         = 2592000
  cache_expiration_time_browser = -1

  # TLS security level: "Compatible" drops TLS 1.0/1.1 and the weak RSA/CBC
  # cipher suites allowed by "Legacy".
  tls_level   = "Compatible"
  tls_support = []

  # A new name replaces the pull zone (system hostname <name>.b-cdn.net):
  # the new one is created first, then the hostname moves to it.
  lifecycle {
    create_before_destroy = true
  }
}

resource "bunnynet_pullzone_hostname" "this" {
  pullzone    = bunnynet_pullzone.this.id
  name        = local.site.hostname
  tls_enabled = true
  force_ssl   = true
}

# --- Read-only hardening (edge rules, run in priority order) -----------------
# The site is static: nothing a visitor sends may reach anything but a GET.

locals {
  # Inline scripts and handlers exist in the 2000 pages: 'unsafe-inline' stays, nothing from another
  # origin, no eval, no plugin content, no form submission.
  csp_directives = [
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self'",
    "media-src 'self'",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "frame-src 'self'",
    "frame-ancestors 'self'",
    "form-action 'none'",
    "base-uri 'none'",
    "manifest-src 'none'",
    "worker-src 'none'",
  ]
  csp = join("; ", local.csp_directives)

  # /domage/ mod player (chiptune3 / libopenmpt): WebAssembly.compile needs 'wasm-unsafe-eval'.
  # Only this path gets it; 'unsafe-eval' is not granted.
  csp_player = join("; ", [
    for d in local.csp_directives :
    startswith(d, "script-src ") ? "${d} 'wasm-unsafe-eval'" : d
  ])

  html_extensions = ["htm", "html"]
  # Old picture formats of the picture library (Amiga IFF/LBM, PCX, TGA) and archives
  # (wallpapers): download only.
  archive_extensions = ["zip", "iff", "lbm", "pcx", "tga"]
  static_extensions  = ["jpg", "jpeg", "gif", "png", "bmp", "ico", "zip", "iff", "lbm", "pcx", "tga"]
}

# 1. Anything but GET/HEAD/OPTIONS is refused at the edge, before the origin.
resource "bunnynet_pullzone_edgerule" "read_only" {
  pullzone    = bunnynet_pullzone.this.id
  description = "Read-only: block every method except GET, HEAD, OPTIONS"
  enabled     = true
  priority    = 1
  match_type  = "MatchAll"

  triggers = [{
    type       = "RequestMethod"
    match_type = "MatchNone"
    patterns   = ["GET", "HEAD", "OPTIONS"]
    parameter1 = null
    parameter2 = null
  }]

  actions = [{ type = "BlockRequest", parameter1 = null, parameter2 = null, parameter3 = null }]
}

# 2. Security headers on every response.
resource "bunnynet_pullzone_edgerule" "security_headers" {
  pullzone    = bunnynet_pullzone.this.id
  description = "Security headers"
  enabled     = true
  priority    = 2
  match_type  = "MatchAny"

  triggers = [{
    type       = "Url"
    match_type = "MatchAny"
    patterns   = ["*"]
    parameter1 = null
    parameter2 = null
  }]

  actions = [
    { type = "SetResponseHeader", parameter1 = "X-Content-Type-Options", parameter2 = "nosniff", parameter3 = null },
    { type = "SetResponseHeader", parameter1 = "Referrer-Policy", parameter2 = "no-referrer", parameter3 = null },
    { type = "SetResponseHeader", parameter1 = "X-Frame-Options", parameter2 = "SAMEORIGIN", parameter3 = null },
    { type = "SetResponseHeader", parameter1 = "Strict-Transport-Security", parameter2 = "max-age=31536000", parameter3 = null },
    { type = "SetResponseHeader", parameter1 = "Permissions-Policy", parameter2 = "camera=(), microphone=(), geolocation=(), payment=()", parameter3 = null },
  ]
}

# 2b. Cross-origin isolation.
resource "bunnynet_pullzone_edgerule" "isolation" {
  pullzone    = bunnynet_pullzone.this.id
  description = "Cross-origin isolation (COOP/CORP)"
  enabled     = true
  priority    = 3
  match_type  = "MatchAny"

  triggers = [{
    type       = "Url"
    match_type = "MatchAny"
    patterns   = ["*"]
    parameter1 = null
    parameter2 = null
  }]

  actions = [
    { type = "SetResponseHeader", parameter1 = "Cross-Origin-Opener-Policy", parameter2 = "same-origin", parameter3 = null },
    { type = "SetResponseHeader", parameter1 = "Cross-Origin-Resource-Policy", parameter2 = "same-origin", parameter3 = null },
  ]
}

# 3. The pages of 2000 are ISO-8859-1 (every <meta> says so): say it in the
# HTTP header too, or browsers may guess UTF-8 and garble accents.
resource "bunnynet_pullzone_edgerule" "html_charset" {
  pullzone    = bunnynet_pullzone.this.id
  description = "HTML pages: Content-Type with charset iso-8859-1"
  enabled     = true
  priority    = 4
  match_type  = "MatchAny"

  triggers = [{
    type       = "UrlExtension"
    match_type = "MatchAny"
    patterns   = local.html_extensions
    parameter1 = null
    parameter2 = null
  }]

  actions = [
    { type = "SetResponseHeader", parameter1 = "Content-Type", parameter2 = "text/html; charset=iso-8859-1", parameter3 = null },
    { type = "OverrideBrowserCacheTime", parameter1 = "3600", parameter2 = null, parameter3 = null },
  ]
}

# 4. Archives and picture formats no browser shows: never interpreted, always downloaded.
resource "bunnynet_pullzone_edgerule" "archives" {
  pullzone    = bunnynet_pullzone.this.id
  description = "Archives: octet-stream + Content-Disposition attachment"
  enabled     = true
  priority    = 5
  match_type  = "MatchAny"

  triggers = [{
    type       = "UrlExtension"
    match_type = "MatchAny"
    patterns   = local.archive_extensions
    parameter1 = null
    parameter2 = null
  }]

  actions = [
    { type = "SetResponseHeader", parameter1 = "Content-Type", parameter2 = "application/octet-stream", parameter3 = null },
    { type = "SetResponseHeader", parameter1 = "Content-Disposition", parameter2 = "attachment", parameter3 = null },
  ]
}

# 5. Images and archives never change: browsers keep them a week.
resource "bunnynet_pullzone_edgerule" "static_cache" {
  pullzone    = bunnynet_pullzone.this.id
  description = "Images and archives: browser cache 7 days"
  enabled     = true
  priority    = 6
  match_type  = "MatchAny"

  # bunny.net accepts at most 5 patterns per trigger: one trigger per chunk of 5.
  triggers = [for i in range(0, length(local.static_extensions), 5) : {
    type       = "UrlExtension"
    match_type = "MatchAny"
    patterns   = slice(local.static_extensions, i, min(i + 5, length(local.static_extensions)))
    parameter1 = null
    parameter2 = null
  }]

  actions = [{ type = "OverrideBrowserCacheTime", parameter1 = "604800", parameter2 = null, parameter3 = null }]
}

# 7-8. Content-Security-Policy, one rule per path so each response gets exactly one value.
resource "bunnynet_pullzone_edgerule" "csp" {
  pullzone    = bunnynet_pullzone.this.id
  description = "CSP: every path except /domage/ (no WebAssembly)"
  enabled     = true
  priority    = 7
  match_type  = "MatchAll"

  triggers = [{
    type       = "Url"
    match_type = "MatchNone"
    patterns   = ["/domage/*"]
    parameter1 = null
    parameter2 = null
  }]

  actions = [{ type = "SetResponseHeader", parameter1 = "Content-Security-Policy", parameter2 = local.csp, parameter3 = null }]
}

resource "bunnynet_pullzone_edgerule" "csp_player" {
  pullzone    = bunnynet_pullzone.this.id
  description = "CSP: /domage/ mod player (adds wasm-unsafe-eval)"
  enabled     = true
  priority    = 8
  match_type  = "MatchAll"

  triggers = [{
    type       = "Url"
    match_type = "MatchAny"
    patterns   = ["/domage/*"]
    parameter1 = null
    parameter2 = null
  }]

  actions = [{ type = "SetResponseHeader", parameter1 = "Content-Security-Policy", parameter2 = local.csp_player, parameter3 = null }]
}

output "storage_zone_name" {
  value = bunnynet_storage_zone.this.name
}

output "pullzone_id" {
  value = bunnynet_pullzone.this.id
}

output "cdn_hostname" {
  description = "bunny.net system hostname, target of the DNS CNAME record."
  value       = "${bunnynet_pullzone.this.name}.${bunnynet_pullzone.this.cdn_domain}"
}
