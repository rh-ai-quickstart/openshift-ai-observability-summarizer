{{/*
Expand the name of the chart.
*/}}
{{- define "otel-collector.name" -}}
{{- default .Chart.Name .Values.common.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "otel-collector.fullname" -}}
{{- if .Values.common.fullnameOverride }}
{{- .Values.common.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.common.nameOverride }}
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
{{- define "otel-collector.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "otel-collector.labels" -}}
helm.sh/chart: {{ include "otel-collector.chart" . }}
{{ include "otel-collector.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: otel-collector
app.kubernetes.io/part-of: observability
{{- with .Values.common.labels }}
{{- toYaml . | nindent 0 }}
{{- end }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "otel-collector.selectorLabels" -}}
app.kubernetes.io/name: {{ include "otel-collector.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "otel-collector.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "otel-collector.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create the namespace
*/}}
{{- define "otel-collector.namespace" -}}
{{- .Values.global.namespace }}
{{- end }}

{{/*
Create a cluster-scoped resource name that includes namespace to avoid conflicts.
This is used for ClusterRole and ClusterRoleBinding names to ensure uniqueness
across different Helm releases and namespaces.
*/}}
{{- define "otel-collector.clusterResourceName" -}}
{{- $fullname := include "otel-collector.fullname" . -}}
{{- $namespace := include "otel-collector.namespace" . -}}
{{- printf "%s-%s" $namespace $fullname | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Collector labels for main collector
*/}}
{{- define "otel-collector.collectorLabels" -}}
helm.sh/chart: {{ include "otel-collector.chart" . }}
app.kubernetes.io/name: {{ .Values.collector.name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: otel-collector
app.kubernetes.io/part-of: observability
{{- with .Values.common.labels }}
{{- toYaml . | nindent 0 }}
{{- end }}
{{- end }}

{{/*
Generate the Tempo gateway endpoint URL
*/}}
{{- define "otel-collector.tempoGatewayEndpoint" -}}
{{- with .Values.tempo.gateway }}
{{- printf "%s://%s.%s.svc.cluster.local:%s%s" .protocol .endpoint .namespace .port .path }}
{{- end }}
{{- end }}

{{/*
Generate the collector endpoint URL for instrumentation
*/}}
{{- define "otel-collector.collectorEndpoint" -}}
{{- printf "http://%s-collector.%s.svc.cluster.local:4318" .Values.collector.name .Values.global.namespace }}
{{- end }}

{{/*
Common annotations
*/}}
{{- define "otel-collector.annotations" -}}
{{- with .Values.common.annotations }}
{{- toYaml . | nindent 0 }}
{{- end }}
{{- end }}