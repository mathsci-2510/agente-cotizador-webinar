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
> sobre ECR, ECS, IAM, RDS, ElastiCache, Secrets Manager y CloudWatch.

## 0. Prerrequisitos

- Cuenta de AWS con permisos administrativos (o un rol con los servicios
  listados arriba).
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

El repositorio usa **SqliteSaver** como checkpointer (ver `app/main.py`),
adecuado para la demo y para una sola instancia. Para producción con más
de una réplica del contenedor, hay dos ajustes recomendados (no incluidos
en este repo de partida, para no sobre-diseñar antes de tener el caso de
uso real):

- Migrar el checkpointer de conversación a un backend compartido (p. ej.
  `langgraph-checkpoint-postgres` sobre **Amazon RDS**, o un checkpointer
  respaldado en **Amazon ElastiCache (Redis)**).
- Mover `data/quotes` (los PDF generados) a **Amazon S3** en vez del disco
  local del contenedor, y servir la descarga con URLs prefirmadas.

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
| `CHECKPOINT_DB_PATH` | Volumen persistente o, en producción, reemplazado por el backend de RDS/Redis del punto 4 |
| `QUOTES_DIR` | Volumen persistente o, en producción, bucket de S3 |

## 7. Checklist antes del webinar

- [ ] Imagen construida y publicada en ECR.
- [ ] Servicio ECS corriendo y accesible vía el DNS del ALB.
- [ ] `GET /health` responde `{"status":"ok"}` desde la URL pública.
- [ ] Prueba end-to-end de una cotización completa contra la URL pública
      (no solo en `localhost`).
- [ ] Video de respaldo grabado de la demo funcionando (plan de
      contingencia, ver `docs/GUION_WEBINAR.md`).
