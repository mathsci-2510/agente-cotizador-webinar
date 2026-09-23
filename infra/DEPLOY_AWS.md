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

## Estado actual (2026-09-23) y bloqueos de cuenta pendientes

Al intentar ejecutar este plan se encontraron dos bloqueos **a nivel de cuenta**,
no de permisos ni de código, que quedan pendientes de resolución por parte
del autor (no se pueden resolver por CLI):

- **AWS (cuenta 490756899531)**: `aws cloudfront create-distribution` devuelve
  `AccessDenied: Your account must be verified before you can add new
  CloudFront resources`. Se resuelve abriendo un caso en
  `https://support.console.aws.amazon.com/support/home#/case/create`
  ("Account and billing support" → tipo "Account"), solo posible logueado
  como root. Estado: pendiente de confirmar si el caso ya se envió.
- **GCP (cuenta personal `david2510chuquin@gmail.com`, proyecto
  `agente-cotizador-webinar` ya creado)**: `gcloud services enable
  run.googleapis.com` falla con `Billing account ... is not found` — la única
  cuenta de facturación de esa cuenta (`Mi cuenta de facturación`,
  `01CB99-1121DC-4290BD`) está cerrada (`OPEN: False`). Se resuelve
  reactivándola o creando una nueva en `https://console.cloud.google.com/billing`.

**Plan B mientras tanto (activo y probado)**: backend corriendo en local
(`uvicorn app.main:app --port 8080`) expuesto vía **Cloudflare Tunnel**
(`cloudflared tunnel --url http://localhost:8080`, sin cuenta, gratis). Da una
URL pública HTTPS tipo `https://<palabras-random>.trycloudflare.com`.

⚠️ **Es frágil**: la URL cambia cada vez que se reinicia el túnel, y la
conexión se cae si cambia la red, se suspende el equipo, o pasa mucho tiempo
(ya ocurrió una vez en pruebas — Cloudflare mismo advierte "no uptime
guarantee" para túneles sin cuenta). **No dejarlo corriendo días antes del
webinar** — repetir estos pasos justo antes de la demo:

```bash
# 1. Backend
uvicorn app.main:app --port 8080 &

# 2. Túnel (imprime la URL pública nueva cada vez)
cloudflared.exe tunnel --url http://localhost:8080

# 3. Probar antes de salir en vivo
curl https://<la-url-que-imprimió>.trycloudflare.com/health
```

Si el túnel se cae a media demo, el plan de contingencia normal aplica
igual: modo offline + video de respaldo (ver `docs/GUION_WEBINAR.md`).

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

El frontend estático (`demo/index.html` y `presentation/index.html`) se
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

- [ ] Imagen construida y publicada en ECR.
- [ ] Servicio ECS corriendo y accesible vía el DNS del ALB.
- [ ] `GET /health` responde `{"status":"ok"}` desde la URL pública.
- [ ] Prueba end-to-end de una cotización completa contra la URL pública
      (no solo en `localhost`).
- [ ] Video de respaldo grabado de la demo funcionando (plan de
      contingencia, ver `docs/GUION_WEBINAR.md`).
