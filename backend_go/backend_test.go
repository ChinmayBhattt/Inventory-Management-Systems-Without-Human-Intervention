package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"testing"

	"autonomous-inventory-backend-go/backend_go/internal/config"
	"autonomous-inventory-backend-go/backend_go/internal/database"
	"autonomous-inventory-backend-go/backend_go/internal/services"
)

func TestReplenishmentMath(t *testing.T) {
	// Average daily demand = 10, std = 3, lead time = 5 days, lead time std = 1, z = 1.65 (95% service level)
	ss := services.CalculateSafetyStock(10.0, 3.0, 5, 1.0, 1.65)
	if ss <= 0 {
		t.Errorf("Safety stock must be > 0, got %d", ss)
	}

	rop := services.CalculateReorderPoint(10.0, 5, ss)
	expectedLeadDemand := 50
	if rop != expectedLeadDemand+ss {
		t.Errorf("ROP should be lead demand + ss (%d), got %d", expectedLeadDemand+ss, rop)
	}

	// Annual demand = 3650, fixed order cost = $50, unit cost = $20, holding = 20%
	eoq := services.CalculateEOQ(3650.0, 50.0, 20.0, 0.20)
	if eoq <= 0 {
		t.Errorf("EOQ must be > 0, got %d", eoq)
	}
}

func TestShopifyHMACVerification(t *testing.T) {
	cfg := &config.Config{ShopifyWebhookSecret: "test-secret-key-123"}
	orderSvc := services.NewOrderService(nil, cfg)

	rawBody := []byte(`{"id":12345,"total_price":"100.00"}`)
	mac := hmac.New(sha256.New, []byte("test-secret-key-123"))
	mac.Write(rawBody)
	validHMAC := base64.StdEncoding.EncodeToString(mac.Sum(nil))

	if !orderSvc.VerifyShopifySignature(rawBody, validHMAC) {
		t.Errorf("Expected valid HMAC to verify successfully")
	}

	if orderSvc.VerifyShopifySignature(rawBody, "invalid-hmac-signature") {
		t.Errorf("Expected invalid HMAC to fail verification")
	}
}

func TestDatabaseQueries(t *testing.T) {
	db, err := database.Connect("../inventory.db")
	if err != nil {
		t.Skipf("Skipping DB test if inventory.db is not in parent path: %v", err)
		return
	}
	defer db.Close()

	ledgerSvc := services.NewLedgerService(db)
	stocks, err := ledgerSvc.GetStockLevels()
	if err != nil {
		t.Fatalf("Failed to fetch stock levels: %v", err)
	}
	if len(stocks) == 0 {
		t.Errorf("Expected at least one stock level record, got 0")
	}

	authSvc := services.NewAuthService(db, &config.Config{JWTSecret: "test-secret"})
	loginRes, err := authSvc.Login("admin@example.com", "admin123")
	if err != nil {
		t.Fatalf("Failed to login admin: %v", err)
	}
	if loginRes.AccessToken == "" {
		t.Errorf("Expected valid JWT access token, got empty")
	}
}

