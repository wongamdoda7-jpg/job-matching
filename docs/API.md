# Job Matching Platform - API Documentation

## Authentication Endpoints

### User Registration
```
POST /api/auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "secure_password",
  "full_name": "John Doe"
}
```

### User Login
```
POST /api/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "secure_password"
}
```

## Job Endpoints

### List All Jobs
```
GET /api/jobs?page=1&limit=10&location=city&skill=skill_name
```

### Get Job Details
```
GET /api/jobs/:id
```

### Create Job (Employer Only)
```
POST /api/jobs
Authorization: Bearer token
```

## Application Endpoints

### Apply for Job
```
POST /api/applications
Authorization: Bearer token
```

### Get My Applications
```
GET /api/applications/my-applications
Authorization: Bearer token
```