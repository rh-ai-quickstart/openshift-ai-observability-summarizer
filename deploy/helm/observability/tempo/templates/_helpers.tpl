{{/*
Expand the name of the chart.
*/}}
{{- define "tempo-stack.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "tempo-stack.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "tempo-stack.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "tempo-stack.labels" -}}
helm.sh/chart: {{ include "tempo-stack.chart" . }}
{{ include "tempo-stack.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: tempo
app.kubernetes.io/part-of: observability
{{- end }}

{{/*
Selector labels
*/}}
{{- define "tempo-stack.selectorLabels" -}}
app.kubernetes.io/name: {{ include "tempo-stack.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
MinIO labels
*/}}
{{- define "tempo-stack.minioLabels" -}}
helm.sh/chart: {{ include "tempo-stack.chart" . }}
app.kubernetes.io/name: minio-tempo
app.kubernetes.io/instance: {{ .Release.Name }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: storage
app.kubernetes.io/part-of: observability
{{- end }}

{{/*
MinIO selector labels
*/}}
{{- define "tempo-stack.minioSelectorLabels" -}}
app.kubernetes.io/name: minio-tempo
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the namespace
*/}}
{{- define "tempo-stack.namespace" -}}
{{- .Values.global.namespace }}
{{- end }}

{{/*
Create a cluster-scoped resource name that includes namespace to avoid conflicts.
This is used for ClusterRole and ClusterRoleBinding names to ensure uniqueness
across different Helm releases and namespaces.
*/}}
{{- define "tempo-stack.clusterResourceName" -}}
{{- $fullname := include "tempo-stack.fullname" . -}}
{{- $namespace := include "tempo-stack.namespace" . -}}
{{- printf "%s-%s" $namespace $fullname | trunc 63 | trimSuffix "-" }}
{{- end }}