#!/usr/bin/env python3
"""Manual script that verifies local access to Vertex Gemini; not a pytest test."""

import os

from dotenv import load_dotenv
from google import genai

load_dotenv()

project = os.environ["GOOGLE_CLOUD_PROJECT"]
location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

client = genai.Client(
    vertexai=True,
    project=project,
    location=location,
)

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Say OK if Vertex AI works.",
)

print(response.text)
