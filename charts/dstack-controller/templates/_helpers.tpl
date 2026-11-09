{{- define "dstack-controller.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "dstack-controller.selectorLabels" -}}
app.kubernetes.io/name: {{ default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" | quote }}
app.kubernetes.io/instance: {{ .Release.Name | quote }}
{{- end -}}

{{- define "dstack-controller.labels" -}}
{{ include "dstack-controller.selectorLabels" . }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | quote }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service | quote }}
{{- end -}}

{{- define "dstack-controller.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "dstack-controller.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "dstack-controller.image" -}}
{{- if .Values.image.digest -}}
{{- printf "%s@%s" .Values.image.repository .Values.image.digest -}}
{{- else -}}
{{- printf "%s:%s" .Values.image.repository (required "image.tag or image.digest is required" .Values.image.tag) -}}
{{- end -}}
{{- end -}}

{{- define "dstack-controller.serviceDnsNames" -}}
{{- $fullname := include "dstack-controller.fullname" . -}}
{{- $namespace := .Release.Namespace -}}
- {{ $fullname | quote }}
- {{ printf "%s.%s" $fullname $namespace | quote }}
- {{ printf "%s.%s.svc" $fullname $namespace | quote }}
- {{ printf "%s.%s.svc.%s" $fullname $namespace .Values.tls.clusterDomain | quote }}
{{- end -}}

{{/* Files for the TLS sidecar. Rendered once and hashed into the Pod template. */}}
{{- define "dstack-controller.tlsProxyFiles" -}}
nginx.conf: |
  pid /tmp/nginx.pid;
  error_log /dev/stderr warn;
  events {
    worker_connections 256;
  }
  http {
    access_log off;
    server_tokens off;
    client_body_temp_path /tmp/client_temp;
    proxy_temp_path /tmp/proxy_temp;
    fastcgi_temp_path /tmp/fastcgi_temp;
    uwsgi_temp_path /tmp/uwsgi_temp;
    scgi_temp_path /tmp/scgi_temp;
    server {
      listen {{ .Values.tls.port }} ssl;
      ssl_certificate /etc/dstack-tls/tls.crt;
      ssl_certificate_key /etc/dstack-tls/tls.key;
      ssl_protocols TLSv1.2 TLSv1.3;
      location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
        client_max_body_size 16m;
      }
    }
  }
run.sh: |
  # Serve dstack over TLS and reload nginx after cert-manager renews the certificate.
  set -eu
  conf=/etc/dstack-tls-proxy/nginx.conf
  certificate=/etc/dstack-tls/tls.crt
  nginx -c "$conf" -g 'daemon off;' &
  nginx_pid=$!
  # The nginx image stops containers with SIGQUIT; Kubernetes may also send SIGTERM.
  trap 'nginx -c "$conf" -s quit; wait "$nginx_pid"; exit 0' TERM INT QUIT
  current=$(sha256sum "$certificate")
  while kill -0 "$nginx_pid" 2>/dev/null; do
    sleep {{ .Values.tls.proxy.reloadCheckSeconds }} &
    wait $! || true
    next=$(sha256sum "$certificate")
    if [ "$next" != "$current" ]; then
      echo "certificate changed; reloading nginx"
      nginx -c "$conf" -s reload && current=$next
    fi
  done
  wait "$nginx_pid"
{{- end -}}

{{/*
With TLS, dstack listens on 127.0.0.1 only, so an HTTP probe from the kubelet cannot reach it.
Send the same request from inside the container with the image's curl instead.
*/}}
{{- define "dstack-controller.probe" -}}
{{- $probe := .probe -}}
{{- if and .root.Values.tls.enabled $probe.httpGet -}}
{{- $url := printf "http://127.0.0.1:3000%s" (default "/" $probe.httpGet.path) -}}
{{- $exec := dict "command" (list "curl" "--fail" "--silent" "--output" "/dev/null" "--max-time" "5" $url) -}}
{{- $probe = merge (dict "exec" $exec) (omit $probe "httpGet") (dict "timeoutSeconds" 10) -}}
{{- end -}}
{{- toYaml $probe -}}
{{- end -}}
