# XRTourGuide API Documentation

## Overview

The XRTourGuide API provides endpoints for managing augmented reality tours, waypoints, reviews, and related resources.

**Base URL:** `https://xrtourguide.di.unisa.it/`  
**Version:** v1  
**Authentication:** Basic Auth  
**Contact:** isislab.unisa@gmail.com  
**License:** BSD License

---

## Endpoints

### Health Check

#### GET `/health_check/`
Check if the service is active.

**Response:**
- `200`: Service is active
```json
{
  "status": "Active"
}
```

---

### Tours

#### GET `/tour-informations`
Retrieve all tours with streaming links for default images and waypoint resources.

**Response:**
- `200`: List of tours with streaming links and waypoint resources

---

#### GET `/tour_list/`
List tours by category with optional filters.

**Query Parameters:**
- `searchTerm` (string, optional): Keyword to search in title, description, place or coordinates
- `category` (string, optional): Filter tours by category
- `sorted` (string, optional): Sort tours by creation time (true/false)
- `num_tours` (integer, optional): Limit number of tours returned
- `lat` (number, optional): Latitude for distance-based sorting
- `lon` (number, optional): Longitude for distance-based sorting

**Response:**
- `200`: Array of tours

---

#### GET `/tour_details/{id}/`
Retrieve details for a specific tour.

**Path Parameters:**
- `id` (integer, required): ID of the tour

**Response:**
- `200`: Tour details
- `404`: Tour not found

---

#### GET `/tour/{id}/`
Generate deep link page for opening tour in mobile app or web.

**Path Parameters:**
- `id` (integer, required): ID of the tour

**Response:**
- `200`: HTML page with deep link logic

---

#### POST `/increment_view_count/`
Increment the view count for a specific tour.

**Request Body:**
```json
{
  "tour_id": 123
}
```

**Response:**
- `200`: Tour updated successfully
- `404`: Tour not found

---

### Waypoints

#### GET `/tour_waypoints/{tour_id}/`
Retrieve waypoints for a specific tour including sub-tours.

**Path Parameters:**
- `tour_id` (integer, required): ID of the tour

**Response:**
- `200`: Waypoints and sub-tours retrieved successfully
```json
{
  "waypoints": [],
  "sub_tours": []
}
```
- `404`: Tour not found

---

#### GET `/get_waypoint_resources/`
Get waypoint resources by type.

**Query Parameters:**
- `waypoint_id` (string, required): ID of the waypoint
- `resource_type` (string, required): Type of resource (readme/video/audio/pdf/links/images)

**Response:**
- `200`: Resource URLs retrieved successfully
```json
{
  "url": "/stream_minio_resource?waypoint=1&file=readme"
}
```
- `400`: Invalid resource type
- `404`: Waypoint not found

---

#### GET `/stream_minio_resource/`
Stream a specific file from MinIO storage for a waypoint.

**Query Parameters:**
- `file` (string, required): Exact name of the file to stream (pdf/audio/video/readme/image)

**Response:**
- `200`: File streamed successfully
- `400`: File name not provided
- `404`: Waypoint or file not found

---

### Reviews

#### POST `/create_review/`
Create a new review for a specific tour.

**Request Body:**
```json
{
  "tour_id": 123,
  "rating": 4.5,
  "comment": "Great tour!"
}
```

**Response:**
- `201`: Review created successfully
- `404`: Tour not found

---

#### GET `/get_reviews_by_tour_id/{tour_id}/`
Retrieve reviews for a specific tour.

**Path Parameters:**
- `tour_id` (integer, required): ID of the tour

**Response:**
- `200`: List of reviews
- `404`: Tour not found

---

#### GET `/get_reviews_by_user/`
Retrieve all reviews made by the currently logged in user.

**Response:**
- `200`: List of reviews
```json
{
  "review_count": 5,
  "reviews": []
}
```

---

### Model & Inference

#### GET `/download_model/`
Download training data model for a tour.

**Query Parameters:**
- `tour_id` (string, required): ID of the tour

**Response:**
- `200`: Training data retrieved successfully

---

#### GET `/load_model/{tour_id}/`
Load model for a specific tour.

**Path Parameters:**
- `tour_id` (integer, required): ID of the tour

**Response:**
- `200`: Model loaded successfully
- `404`: Tour or model not found

---

#### POST `/inference/`
Run inference on an image for a specific tour.

**Request Body:**
```json
{
  "tour_id": 123,
  "img": "base64_encoded_image_data"
}
```

**Response:**
- `200`: Inference completed
```json
{
  "result": 1,
  "available_resources": {
    "pdf": 1,
    "readme": 0,
    "video": 1,
    "audio": 0,
    "links": 1
  }
}
```
- `404`: Tour not found

---

### Build & Map

#### POST `/complete_build/`
Complete the build process for a tour.

**Request Body:**
```json
{
  "poi_name": "Tour Name",
  "poi_id": 123,
  "model_url": "https://example.com/model.zip",
  "status": "COMPLETED"
}
```

**Response:**
- `200`: Build completed successfully
- `404`: Tour not found
- `500`: Error saving tour

---

#### POST `/cut_map/{tour_id}/`
Extract and download pmtiles file for a tour based on waypoint coordinates.

**Path Parameters:**
- `tour_id` (integer, required): ID of the tour

**Response:**
- `200`: Pmtiles file returned successfully
- `400`: Tour not found or invalid waypoints

---

## Data Models

### Tour
```json
{
  "id": 123,
  "title": "Tour Title",
  "subtitle": "Tour Subtitle",
  "place": "Location Name",
  "category": "INSIDE|OUTDOOR|THING|MIXED",
  "description": "Tour description",
  "user": 456,
  "lat": "40.7128",
  "lon": "-74.0060",
  "default_img": "image_url",
  "creation_time": "2024-01-01T12:00:00Z",
  "user_name": "username",
  "tot_view": 100,
  "l_edited": "2024-01-01T12:00:00Z",
  "rating": "4.5",
  "rating_counter": "10"
}
```

### Review
```json
{
  "id": 789,
  "tour": 123,
  "user": 456,
  "rating": 5,
  "comment": "Amazing experience!",
  "user_name": "username",
  "creation_date": "2024-01-01T12:00:00Z"
}
```

---

## Authentication

All endpoints require Basic Authentication. Include credentials in the request header:

```
Authorization: Basic <base64_encoded_credentials>
```

---

## Error Responses

Common error responses across endpoints:

- `400`: Bad Request - Invalid parameters or missing required fields
- `404`: Not Found - Requested resource does not exist
- `500`: Internal Server Error - Server-side error occurred
