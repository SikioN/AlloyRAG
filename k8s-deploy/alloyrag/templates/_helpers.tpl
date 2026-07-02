{{/*
Application name
*/}}
{{- define "alloyrag.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Full application name
*/}}
{{- define "alloyrag.fullname" -}}
{{- default .Release.Name .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "alloyrag.labels" -}}
app.kubernetes.io/name: {{ include "alloyrag.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "alloyrag.selectorLabels" -}}
app.kubernetes.io/name: {{ include "alloyrag.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
.env file content
*/}}
{{- define "alloyrag.envContent" -}}
{{- $first := true -}}
{{- range $key, $val := .Values.env -}}
{{- if not $first -}}{{- "\n" -}}{{- end -}}
{{- $first = false -}}
{{ $key }}={{ $val }}
{{- end -}}
{{- end -}}
