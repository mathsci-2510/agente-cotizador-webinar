# Despliegue en AWS — guía de referencia

Este documento resume los pasos para llevar el agente (ya funcional en local,
ver `README.md`) a producción en AWS, siguiendo la arquitectura descrita en
la propuesta del webinar (Figura 1: Cliente → API REST → Orquestador → LLM
→ Persistencia → Infraestructura AWS).

> **Nota para continuar con Claude Code**: abre este repositorio con Claude
> Code y pídele explícitamente "conéctate a mi cuenta de AWS y despliega el
> agente siguiendo infra/DEPLOY_AWS.md". Claude necesitará que tengas
> configuradas credenciales de AWS (`aws configure` o variables
> `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_REGION`) con permisos
> sobre ECR, ECS, IAM, S3, CloudFront, Secrets Manager y CloudWatch.

## Estado actual (2026-09-23): desplegado y probado, arquitectura final

Tras encontrar bloqueos de verificación de cuenta en ambos AWS y GCP
(historial abajo), la arquitectura que quedó **desplegada, probada de punta
a punta y en uso real** es:

```
Cliente → CloudFront (AWS, gratis) → Render.com free tier (backend FastAPI/LangGraph)
```

- **Backend**: Render.com, plan free, desplegado desde
  `https://github.com/mathsci-2510/agente-cotizador-webinar` (build automático
  desde el `Dockerfile` vía `render.yaml`). URL directa:
  `https://agente-cotizador-webinar.onrender.com`.
- **CDN/entrada pública en AWS**: distribución de CloudFront
  `E3DFO5Y77NOIIO`, dominio `https://d2huls6tugzwwb.cloudfront.net`, origen
  custom apuntando al backend de Render. **Importante**: usa la política de
  origin request **`Managed-AllViewerExceptHostHeader`**
  (`b689b0a8-53d0-40ab-baf2-68738e2966ac`), no `AllViewer` — con `AllViewer`
  CloudFront reenvía el header `Host` del visitante (el dominio de
  CloudFront) en vez del de Render, y Render (multi-tenant) responde 502
  porque no reconoce ese host. Cache policy: `CachingDisabled` (API dinámica).
- **Costo real**: ambos servicios están dentro de su free tier permanente
  (CloudFront: 1TB/10M requests al mes, siempre gratis; Render free web
  service: 750h/mes, sin tarjeta). Costo esperado: **USD 0**.
- **Limitación conocida de Render free**: el servicio "duerme" tras ~15 min
  sin tráfico y tarda hasta ~1 min en responder la primera petición tras
  despertar (ya observado en pruebas: un `curl` con timeout corto dio
  timeout, con más tiempo respondió 200 normalmente). Antes del webinar,
  hacer un `GET /health` unos minutos antes de salir en vivo para
  "despertarlo".
- **Variables de entorno pendientes de cargar en el dashboard de Render**
  (quedaron como `sync: false` en `render.yaml` a propósito, para no
  comprometerlas en git): `OPENAI_API_KEY` (opcional, si se quiere modo LLM
  en vivo) y `REDIS_URL` (para que el checkpointer use Redis Cloud en vez de
  SQLite efímero del contenedor). Mientras no se carguen, el agente corre en
  modo offline con SQLite — que es exactamente el plan de contingencia, así
  que es una configuración válida para el webinar tal cual está.

### Historial de bloqueos encontrados (ya resueltos o descartados)

- **AWS (cuenta 490756899531)**: al principio `aws cloudfront
  create-distribution` devolvía `AccessDenied: Your account must be verified
  before you can add new CloudFront resources`. Se resolvió después de que
  el autor gestionara la verificación de la cuenta — un reintento posterior
  del mismo comando ya funcionó y creó la distribución sin cambios de
  permisos de por medio.
- **GCP (Cloud Run)**: descartado como opción — la cuenta personal
  (`david2510chuquin@gmail.com`, proyecto `agente-cotizador-webinar`, ya
  creado por si se retoma) no tenía cuenta de facturación activa, y
  reactivarla implicaba un cargo de verificación de tarjeta que el autor
  prefirió evitar. Se optó por Render en su lugar (sin tarjeta).
- **ECS Fargate + ALB** (plan original de las secciones 1-3 de abajo): no
  se llegó a necesitar — Render + CloudFront resultó suficiente y gratis
  para el alcance de un webinar de 45 minutos. Las secciones siguientes se
  dejan como referencia si en el futuro se requiere una arquitectura 100%
  AWS (más control, pero con costo real de ALB/Fargate, ver sección 3).

## 0. Prerrequisitos

- Cuenta de AWS con permisos administrativos (o un rol con los servicios
  listados arriba).
- **Cuenta correcta**: este proyecto se despliega en la cuenta personal del
  autor (usuario IAM `mathsci`), **no** en la cuenta de Pentamédica. Si el
  entorno tiene varios perfiles de AWS CLI configurados, usar explícitamente
  `--profile davidl2510` (o el perfil que en ese momento apunte a la cuenta
  personal) en cada comando — nunca el perfil `default`/`sso-david` sin
  verificar antes con `aws sts get-caller-identity --profile <perfil>` a qué
  cuenta apunta.
- AWS CLI v2 instalado y autenticado (`aws sts get-caller-identity` debe
  responder correctamente).
- Docker instalado localmente para construir la imagen.
- Una API key de OpenAI (si se quiere ejecutar en modo LLM; en modo
  offline el agente funciona igual, sin esta key).

## 1. Contenerización y registro (ECR)

```bash
aws ecr create-repository --repository-name agente-cotizador-equipos-medicos

aws ecr get-login-password --region <REGION> | \
  docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com

docker build -t agente-cotizador-equipos-medicos .
docker tag agente-cotizador-equipos-medicos:latest \
  <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/agente-cotizador-equipos-medicos:latest

docker push <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/agente-cotizador-equipos-medicos:latest
```

## 2. Secreto de la API key (Secrets Manager)

```bash
aws secretsmanager create-secret \
  --name agente-cotizador/openai-api-key \
  --secret-string '{"OPENAI_API_KEY":"sk-..."}'
```

## 3. Cómputo (ECS Fargate + ALB)

- Crear un clúster ECS (`aws ecs create-cluster`).
- Definir una *task definition* Fargate que use la imagen publicada en ECR,
  puerto de contenedor `8080`, y que inyecte `OPENAI_API_KEY` desde el
  secreto anterior (`secrets` en la task definition, no como variable de
  entorno plana).
- Crear un *Application Load Balancer* (ALB) con un *target group* HTTP
  hacia el puerto 8080 del servicio ECS.
- Crear el servicio ECS (`desired-count` >= 1, autoscaling opcional según
  CPU/memoria).

## 4. Persistencia para producción

El checkpointer de conversación soporta dos backends (ver `app/main.py` y
`app/config.py`):

- **Sin `REDIS_URL`** → `SqliteSaver` local. Sirve para la demo con una sola
  réplica del contenedor.
- **Con `REDIS_URL`** → `RedisSaver` (`langgraph-checkpoint-redis`), que sí
  soporta múltiples réplicas del contenedor detrás del ALB. Ya está probado
  contra una instancia de **Redis Cloud** externa a AWS (requiere Redis 8+ o
  Redis Stack/RediSearch+RedisJSON — Redis Cloud lo trae por defecto). En
  producción, `REDIS_URL` se inyecta como secreto desde Secrets Manager
  (igual que `OPENAI_API_KEY`, ver punto 2), nunca como variable de entorno
  plana. Alternativa 100% dentro de AWS si se prefiere no depender de un
  proveedor externo: **Amazon ElastiCache (Redis)** — mismo código, solo
  cambia el host en `REDIS_URL`.
- Mover `data/quotes` (los PDF generados) a **Amazon S3** en vez del disco
  local del contenedor, y servir la descarga con URLs prefirmadas, sigue
  pendiente (no incluido en este repo de partida, para no sobre-diseñar
  antes de tener el caso de uso real).

## 4bis. Frontend estático (presentación + demo web) vía S3 + CloudFront

El frontend estático (`demo/index.html` y `presentation/presentacion_webinar.html`) se
despliega **por separado** del backend, en un bucket S3 privado servido por
una distribución de CloudFront (mismo patrón que ya usa el autor en otros
proyectos: S3 + CloudFront, invalidando la caché en cada deploy). El backend
FastAPI (`/chat`, `/health`, `/cotizaciones/*`) sigue expuesto directamente
por el ALB del punto 3 — CloudFront **no** hace de proxy del API en esta
arquitectura, para mantenerla simple y barata:

```bash
aws s3 mb s3://<bucket-frontend> --profile davidl2510
aws s3 sync demo/ s3://<bucket-frontend>/demo/ --profile davidl2510
aws s3 sync presentation/ s3://<bucket-frontend>/presentation/ --profile davidl2510
# Crear la distribución de CloudFront apuntando al bucket (origin access
# control, no público directo) y, tras cada deploy:
aws cloudfront create-invalidation --distribution-id <ID> --paths "/*" --profile davidl2510
```

El `demo/index.html` estático deberá apuntar al endpoint del ALB (variable
o constante configurable) en vez de asumir que la API vive en el mismo
origen, ya que ahora frontend y backend están en dominios distintos.

## 5. Observabilidad

- Los logs de `uvicorn`/`app.*` van a stdout/stderr, por lo que ECS los
  envía automáticamente a **CloudWatch Logs** sin configuración adicional
  (basta con habilitar el *log driver* `awslogs` en la task definition).
- Configurar una alarma de CloudWatch sobre el healthcheck `/health`.

## 6. Variables de entorno esperadas en producción

| Variable | Origen recomendado en AWS |
|---|---|
| `OPENAI_API_KEY` | Secrets Manager (inyectada como `secrets` en la task definition) |
| `OPENAI_MODEL`, `OPENAI_TEMPERATURE` | Variables de entorno normales de la task definition |
| `REDIS_URL` | Secrets Manager (misma lógica que `OPENAI_API_KEY` — contiene credenciales) |
| `CHECKPOINT_DB_PATH` | Solo se usa si `REDIS_URL` no está definida (fallback SQLite de una réplica) |
| `QUOTES_DIR` | Volumen persistente o, en producción, bucket de S3 |

## 7. Checklist antes del webinar

Arquitectura real en uso (Render + CloudFront, ver sección de Estado actual):

- [x] Backend construido y desplegado en Render (`agente-cotizador-webinar.onrender.com`).
- [x] Distribución de CloudFront creada y en `Deployed`
      (`d2huls6tugzwwb.cloudfront.net`, id `E3DFO5Y77NOIIO`).
- [x] `GET /health` responde `{"status":"ok"}` desde la URL pública de CloudFront.
- [x] Prueba end-to-end de una cotización completa (equipo → cantidad →
      ciudad → nombre → contacto → PDF) contra la URL pública de CloudFront,
      no solo en `localhost`.
- [ ] Cargar `OPENAI_API_KEY` y/o `REDIS_URL` en el dashboard de Render si se
      quiere modo LLM y/o checkpointer compartido (opcional — el modo offline
      con SQLite ya funciona y es el plan de contingencia).
- [ ] Hacer un `GET /health` unos minutos antes de salir en vivo, para
      "despertar" a Render si estuvo dormido por inactividad.
- [ ] Video de respaldo grabado de la demo funcionando (plan de
      contingencia, ver `docs/GUION_WEBINAR.md`).
