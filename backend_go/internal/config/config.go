package config

import (
	"bufio"
	"os"
	"strings"
)

type Config struct {
	Environment          string
	Port                 string
	DatabaseURL          string
	JWTSecret            string
	ShopifyWebhookSecret string
	SlackWebhookURL      string
	APIV1Prefix          string
}

func LoadConfig() *Config {
	cfg := &Config{
		Environment:          "development",
		Port:                 "8000",
		DatabaseURL:          "./inventory.db",
		JWTSecret:            "super-secret-development-jwt-key-change-in-production-32chars",
		ShopifyWebhookSecret: "7418a880c2bee66107c4f4006d0ad0bd24e36f666b2ec0f2443b70970b1d9d4f",
		SlackWebhookURL:      "",
		APIV1Prefix:          "/api/v1",
	}

	loadEnvFile(".env", cfg)

	if env := os.Getenv("PORT"); env != "" {
		cfg.Port = env
	}
	if env := os.Getenv("DATABASE_URL"); env != "" {
		cfg.DatabaseURL = cleanDBPath(env)
	}
	if env := os.Getenv("JWT_SECRET_KEY"); env != "" {
		cfg.JWTSecret = env
	}
	if env := os.Getenv("SHOPIFY_WEBHOOK_SECRET"); env != "" {
		cfg.ShopifyWebhookSecret = env
	}
	if env := os.Getenv("SLACK_WEBHOOK_URL"); env != "" {
		cfg.SlackWebhookURL = env
	}

	return cfg
}

func loadEnvFile(path string, cfg *Config) {
	file, err := os.Open(path)
	if err != nil {
		return
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			continue
		}
		key := strings.TrimSpace(parts[0])
		val := strings.Trim(strings.TrimSpace(parts[1]), `"'`)

		switch key {
		case "PORT":
			cfg.Port = val
		case "DATABASE_URL", "SYNC_DATABASE_URL":
			cfg.DatabaseURL = cleanDBPath(val)
		case "JWT_SECRET_KEY":
			cfg.JWTSecret = val
		case "SHOPIFY_WEBHOOK_SECRET":
			cfg.ShopifyWebhookSecret = val
		case "SLACK_WEBHOOK_URL":
			cfg.SlackWebhookURL = val
		case "ENVIRONMENT":
			cfg.Environment = val
		}
	}
}

func cleanDBPath(url string) string {
	url = strings.TrimPrefix(url, "sqlite+aiosqlite:///")
	url = strings.TrimPrefix(url, "sqlite:///")
	url = strings.TrimPrefix(url, "sqlite://")
	return url
}

