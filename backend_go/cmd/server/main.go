package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"autonomous-inventory-backend-go/backend_go/internal/api"
	"autonomous-inventory-backend-go/backend_go/internal/config"
	"autonomous-inventory-backend-go/backend_go/internal/database"
	"autonomous-inventory-backend-go/backend_go/internal/services"
)

func main() {
	log.Println("=================================================================")
	log.Println("🚀 Starting Autonomous Inventory Management System (Go Engine)...")
	log.Println("=================================================================")

	// 1. Load configuration from .env
	cfg := config.LoadConfig()
	log.Printf("[Config] Loaded environment: %s, Port: %s", cfg.Environment, cfg.Port)

	// 2. Connect to SQLite database
	db, err := database.Connect(cfg.DatabaseURL)
	if err != nil {
		log.Fatalf("[Database] Fatal connection error: %v", err)
	}
	defer db.Close()

	// 3. Initialize Services
	authSvc := services.NewAuthService(db, cfg)
	ledgerSvc := services.NewLedgerService(db)
	orderSvc := services.NewOrderService(db, cfg)
	replenishSvc := services.NewReplenishmentService(db)
	poSvc := services.NewPOService(db)
	anomalySvc := services.NewAnomalyService(db, cfg)
	forecastSvc := services.NewForecastService(db)
	grnSvc := services.NewGoodsReceiptService(db, ledgerSvc)

	// 4. Initialize Handlers and HTTP Router
	handlers := api.NewHandlers(
		cfg,
		authSvc,
		ledgerSvc,
		orderSvc,
		replenishSvc,
		poSvc,
		anomalySvc,
		forecastSvc,
		grnSvc,
	)
	router := api.NewRouter(handlers)

	// 5. Configure HTTP Server
	serverAddr := fmt.Sprintf("0.0.0.0:%s", cfg.Port)
	srv := &http.Server{
		Addr:         serverAddr,
		Handler:      router,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	// 6. Channel for graceful shutdown
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)

	go func() {
		log.Printf("🔥 AutoStock AI Go Server listening on http://%s", serverAddr)
		log.Printf("👉 Health check: http://localhost:%s/health", cfg.Port)
		log.Printf("👉 API v1 Base: http://localhost:%s/api/v1", cfg.Port)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Server ListenAndServe error: %v", err)
		}
	}()

	<-stop
	log.Println("\n[Shutdown] Shutting down server gracefully...")

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		log.Printf("[Shutdown] Server forced to shutdown: %v", err)
	}
	log.Println("[Shutdown] Server exited cleanly. Bye!")
}
