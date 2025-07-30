{{/*
Common labels
*/}}
{{- define "metric-ui.labels" -}}
{{ include "metric-ui.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "metric-ui.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- with .Values.labels }}
{{- toYaml . }}
{{- end }}
{{- end }} 