# A-Patricia Agent 🛒

[![Build and Publish Docker Image](https://github.com/Alberth121484/a-patricia/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/Alberth121484/a-patricia/actions/workflows/docker-publish.yml)

**Agente de validación de precios para tiendas retail con búsqueda semántica.**

Analiza fotos de estantes de productos, extrae nombres y precios, y los compara contra una base de datos vectorial (Qdrant) usando búsqueda semántica para encontrar coincidencias incluso cuando los nombres no son exactos.

## 🚀 Características

- **Análisis de imágenes con IA**: Usa Gemini Vision para extraer productos y precios de fotos de estantes
- **Búsqueda semántica**: Usa Qdrant + embeddings para matching fuzzy de productos (resuelve el problema de nombres no coincidentes)
- **Interfaz Web de administración**: Panel para subir/gestionar archivos de productos con autenticación JWT
- **Múltiples formatos**: Soporta CSV, Excel, PDF, TXT, DOCX, imágenes
- **Almacenamiento seguro**: MinIO para archivos con encriptación de datos
- **Integración con Slack**: Responde directamente en canales de Slack
- **Alta concurrencia**: Soporta múltiples solicitudes simultáneas

## 📋 Requisitos

- Docker y Docker Compose
- Red Docker `tiendasneto` (existente)
- Credenciales de Slack Bot
- API Key de Gemini

## 🔧 Configuración

### 1. Crear archivo de entorno

```bash
cp .env.example .env
```

### 2. Configurar Slack App

1. Ve a https://api.slack.com/apps
2. Crea una nueva app o usa una existente
3. Habilita **Socket Mode** en Settings > Socket Mode
4. Crea un **App-Level Token** con scope `connections:write`
5. En **OAuth & Permissions**, agrega estos scopes:
   - `channels:history`
   - `channels:read`
   - `chat:write`
   - `files:read`
   - `reactions:read`
   - `reactions:write`
   - `users:read`
6. En **Event Subscriptions**, suscríbete a:
   - `message.channels`
   - `message.groups`
   - `message.im`
   - `app_mention`
7. Instala la app en tu workspace
8. Copia los tokens al archivo `.env`

### 3. Configurar Gemini

Opción A - API Key:
```env
GEMINI_API_KEY=tu-api-key-de-gemini
```

Opción B - Service Account (si ya tienes uno para BigQuery):
```env
GOOGLE_APPLICATION_CREDENTIALS_JSON={"type":"service_account",...}
```

### 4. Verificar BigQuery

Asegúrate de que el service account tenga acceso a:
- Proyecto: `neto-cloud`
- Dataset: `agente_rebeca`
- Tabla: `tiendas_articulos_precio`

## 🚀 Despliegue

### Opción 1: Usar imagen de GitHub Packages (Recomendado)

```bash
# Descargar imagen
docker pull ghcr.io/alberth121484/a-patricia:latest

# Copiar .env.example a .env y configurar
cp .env.example .env

# Iniciar con docker-compose de producción
docker-compose -f docker-compose.prod.yml up -d
```

### Opción 2: Construir localmente

```bash
docker-compose build
docker-compose up -d
```

### Ver logs

```bash
docker-compose logs -f a-patricia-agent
```

### Verificar salud

```bash
curl http://localhost:1405/health
```

## 🔄 CI/CD con GitHub Actions

La imagen se construye y publica automáticamente en GitHub Container Registry cuando:
- Se hace push a `main` o `master`
- Se crea un tag de versión (ej: `v1.0.0`)

Para publicar una nueva versión:
```bash
git tag v1.0.0
git push origin v1.0.0
```

## 📱 Uso desde Slack

### Validar precios de un estante

1. Sube una foto del estante al canal donde está el bot
2. Incluye el número de tienda en el mensaje

```
Tienda 810
[imagen adjunta]
```

### Buscar un producto específico

```
buscar LECHE LALA tienda 810
```

### Ver ayuda

```
hola
```

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────────────────┐
│                         DOCKER COMPOSE                               │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────┐ │
│  │ A-PATRICIA   │  │   QDRANT     │  │    MINIO     │  │WEB-ADMIN│ │
│  │ (Slack Bot)  │  │ (Vector DB)  │  │  (Storage)   │  │(React)  │ │
│  │ :8080        │  │ :6333        │  │ :9000/:9001  │  │:3000    │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └────┬────┘ │
│         │                 │                 │               │      │
│         └─────────────────┴─────────────────┴───────────────┘      │
│                      Red interna: a-patricia-net                    │
└─────────────────────────────────────────────────────────────────────┘
```

### Flujo de Validación (Slack Bot)

```
Usuario (Slack) ──► SlackHandler ──► VisionService (Gemini)
                                            │
                                            ▼
                                    Extrae productos
                                            │
                                            ▼
                         ┌──────────────────────────────────┐
                         │      QdrantService               │
                         │  - Genera embeddings             │
                         │  - Búsqueda semántica            │
                         │  - Encuentra productos similares │
                         └──────────────────────────────────┘
                                            │
                                            ▼
                                    PriceValidator
                                            │
                                            ▼
                              Respuesta a Slack ✅/❌
```

### Flujo de Administración (Web Admin)

```
Admin ──► Login (JWT) ──► Upload archivo ──► FileProcessor
                                                   │
                                    ┌──────────────┴──────────────┐
                                    │                             │
                                    ▼                             ▼
                               MinIO                          Qdrant
                          (Guarda archivo)            (Indexa productos)
```

## ⚡ Ventajas de la Búsqueda Semántica

| Problema con BigQuery | Solución con Qdrant |
|----------------------|---------------------|
| "LECHE LALA 1L" ≠ "LECHE LALA 1 LITRO" | Encuentra coincidencias por similitud semántica |
| Requiere nombres exactos | Tolera variaciones en nombres |
| Consultas SQL lentas | Búsqueda vectorial rápida |
| Sin contexto semántico | Entiende significado de palabras |

## 🔍 Troubleshooting

### El bot no responde

1. Verifica que Socket Mode esté habilitado
2. Revisa los logs: `docker-compose logs -f a-patricia-agent`
3. Confirma que el bot esté en el canal

### Error de Gemini

1. Verifica que `GEMINI_API_KEY` sea válido
2. Confirma que el modelo `gemini-2.5-flash` esté disponible

### Productos no encontrados

1. Verifica que haya productos indexados en Qdrant
2. Accede a Web Admin y sube un archivo de productos
3. Ajusta `SIMILARITY_THRESHOLD` si es muy estricto (default: 0.7)

### Error de conexión a Qdrant

1. Verifica que el contenedor esté corriendo: `docker-compose ps`
2. Revisa los logs: `docker-compose logs -f qdrant`
3. Verifica `QDRANT_HOST` y `QDRANT_PORT`

## 📄 Licencia

Uso interno - Tiendas Neto
