"""Tests for listings API."""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models.agent import Agent
from app.models.listing import ListingStatus

from tests.conftest import TestingSessionLocal

client = TestClient(app)


def _create_agent() -> int:
    db = TestingSessionLocal()
    agent = Agent(
        name="Listing Agent",
        email="listing@example.com",
        phone="+1111111111",
        whatsapp_number="whatsapp:+1111111111",
    )
    db.add(agent)
    db.commit()
    agent_id = agent.id
    db.close()
    return agent_id


class TestListingsCRUD:
    def test_create_listing(self):
        agent_id = _create_agent()
        resp = client.post("/listings/", json={
            "agent_id": agent_id,
            "address": "123 Main St, Springfield",
            "price": 450000.0,
            "bedrooms": 3,
            "bathrooms": 2,
            "description": "Beautiful family home with garden.",
            "media_urls": ["https://example.com/photo.jpg"],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["address"] == "123 Main St, Springfield"
        assert data["price"] == 450000.0
        assert data["status"] == "draft"

    def test_create_listing_unknown_agent(self):
        resp = client.post("/listings/", json={
            "agent_id": 9999,
            "address": "456 Nowhere Rd",
            "price": 100000.0,
            "description": "Test",
        })
        assert resp.status_code == 404

    def test_get_listing(self):
        agent_id = _create_agent()
        create_resp = client.post("/listings/", json={
            "agent_id": agent_id,
            "address": "789 Oak Ave",
            "price": 320000.0,
            "description": "Cozy cottage",
        })
        listing_id = create_resp.json()["id"]

        resp = client.get(f"/listings/{listing_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == listing_id

    def test_get_listing_not_found(self):
        resp = client.get("/listings/99999")
        assert resp.status_code == 404

    def test_update_listing_status(self):
        agent_id = _create_agent()
        create_resp = client.post("/listings/", json={
            "agent_id": agent_id,
            "address": "1 Test Blvd",
            "price": 500000.0,
            "description": "Test listing",
        })
        listing_id = create_resp.json()["id"]

        resp = client.patch(f"/listings/{listing_id}", json={"status": "active"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    def test_update_media_urls(self):
        agent_id = _create_agent()
        create_resp = client.post("/listings/", json={
            "agent_id": agent_id,
            "address": "2 Media Ln",
            "price": 250000.0,
            "description": "Has media",
            "media_urls": [],
        })
        listing_id = create_resp.json()["id"]

        resp = client.patch(f"/listings/{listing_id}", json={
            "media_urls": ["https://example.com/a.jpg", "https://example.com/b.jpg"]
        })
        assert resp.status_code == 200
        media = json.loads(resp.json()["media_urls"])
        assert len(media) == 2

    def test_list_listings_by_agent(self):
        agent_id = _create_agent()
        for i in range(3):
            client.post("/listings/", json={
                "agent_id": agent_id,
                "address": f"{i} Test St",
                "price": 100000.0 * (i + 1),
                "description": f"Listing {i}",
            })

        resp = client.get(f"/listings/?agent_id={agent_id}")
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    def test_delete_listing(self):
        agent_id = _create_agent()
        create_resp = client.post("/listings/", json={
            "agent_id": agent_id,
            "address": "Delete Me Lane",
            "price": 1.0,
            "description": "Temp",
        })
        listing_id = create_resp.json()["id"]

        del_resp = client.delete(f"/listings/{listing_id}")
        assert del_resp.status_code == 204

        get_resp = client.get(f"/listings/{listing_id}")
        assert get_resp.status_code == 404
