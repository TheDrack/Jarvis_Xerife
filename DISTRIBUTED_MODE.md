# Jarvis Distributed Mode Setup

This document explains how to configure and run Jarvis in distributed mode, where the API runs in the cloud (e.g., Render.com) and the worker runs on your local PC.

## Architecture

```
┌─────────────────┐         ┌──────────────────┐
│   Cloud (API)   │         │  Database (PG)   │
│  - FastAPI      │◄───────►│  - Supabase      │
│  - Creates      │         │  - Stores tasks  │
│    tasks        │         │                  │
└─────────────────┘         └──────────────────┘
                                     ▲
                                     │
                                     │ Polls for
                                     │ pending tasks
                                     │
                            ┌────────┴─────────┐
                            │   Local PC       │
                            │  - Worker        │
                            │  - PyAutoGUI     │
                            │  - Executes      │
                            │    commands      │
                            └──────────────────┘
```

## Setup Instructions

### 1. Database Setup (Supabase)

1. Create a free account at [Supabase](https://supabase.com)
2. Create a new project
3. Get your connection string from Settings → Database
4. The URL format is:
   ```
   postgresql://postgres:YOUR_PASSWORD@db.YOUR_PROJECT_REF.supabase.co:5432/postgres
   ```

### 2. Cloud Deployment (Render.com)

1. Fork/Clone this repository
2. Create a new Web Service on Render.com
3. Configure environment variables:
   ```
   DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@db.YOUR_PROJECT_REF.supabase.co:5432/postgres
   SECRET_KEY=your-secret-key-change-this-in-production-minimum-32-characters
   API_HOST=0.0.0.0
   API_PORT=8000
   ```
4. Set build command: `pip install -r requirements/core.txt`
5. Set start command: `python serve.py`
6. Deploy!

The Dockerfile is already configured to run the API server using the `cloud` stage.

### 3. Local Worker Setup (Your PC)

1. Clone the repository on your local PC
2. Install dependencies:
   ```bash
   pip install -r requirements/edge.txt
   ```
3. Create a `.env` file with the same `DATABASE_URL`:
   ```env
   DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@db.YOUR_PROJECT_REF.supabase.co:5432/postgres
   ```
4. Run the worker:
   ```bash
   python worker_pc.py
   ```

The worker will:
- Poll the database every 2 seconds
- Pick up pending commands
- Execute them using PyAutoGUI
- Update the status to `completed` or `failed`

## Using the Distributed System

### Creating Tasks via API

You can create tasks using the `/v1/task` endpoint:

```bash
# Get authentication token
curl -X POST "https://your-app.onrender.com/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin123"

# Create a task
curl -X POST "https://your-app.onrender.com/v1/task" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"command": "digite hello world"}'

# Response:
# {
#   "task_id": 1,
#   "status": "pending",
#   "message": "Task created successfully with ID 1"
# }
```

### Direct Execution (Legacy Mode)

The `/v1/execute` endpoint still works for direct execution if you run the API server on your PC:

```bash
curl -X POST "http://localhost:8000/v1/execute" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"command": "digite hello world"}'
```

## Monitoring

### Worker Logs

The worker logs are saved to `logs/jarvis_worker.log`. You can monitor them:

```bash
tail -f logs/jarvis_worker.log
```

### API Logs

On Render.com, you can view API logs in the dashboard under the "Logs" tab.

### Database

You can query the database directly to see task status:

```sql
SELECT id, user_input, status, processed_at, success
FROM interactions
WHERE status = 'pending'
ORDER BY timestamp ASC;
```

## Security Considerations

1. **Change the SECRET_KEY**: Generate a strong random key:
   ```bash
   openssl rand -hex 32
   ```

2. **Database Connection**: Always use SSL for database connections in production

3. **API Authentication**: The default credentials (admin/admin123) should be changed in production

4. **Environment Variables**: Never commit `.env` files or expose database credentials

## Troubleshooting

### Worker not picking up tasks

1. Check the database connection:
   ```python
   python -c "from app.adapters.infrastructure.sqlite_history_adapter import SQLiteHistoryAdapter; db = SQLiteHistoryAdapter(database_url='YOUR_URL'); print('Connected!')"
   ```

2. Check if there are pending tasks in the database

3. Check worker logs for errors

### API not creating tasks

1. Verify the `/v1/task` endpoint is available:
   ```bash
   curl https://your-app.onrender.com/docs
   ```

2. Check if the database is accessible from the cloud

3. Check API logs for errors

## Development vs Production

### Development (Local)

- Use SQLite: `DATABASE_URL=sqlite:///jarvis.db`
- Run both API and worker locally
- No need for cloud deployment

### Production (Cloud + PC)

- Use PostgreSQL (Supabase)
- API in the cloud (Render.com)
- Worker on local PC
- Configure environment variables properly

## Next Steps

1. **Add webhooks**: Get notified when tasks are completed
2. **Add task queue**: Use Redis for better task management
3. **Add monitoring**: Use Sentry or similar for error tracking
4. **Add metrics**: Track task completion times and success rates
