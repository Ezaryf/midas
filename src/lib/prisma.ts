import { PrismaClient } from "@prisma/client";
import { PrismaMariaDb } from "@prisma/adapter-mariadb";

declare global {
  var __midasPrisma__: PrismaClient | undefined;
}

export function getPrismaClient(): PrismaClient {
  if (!process.env.DATABASE_URL) {
    throw new Error("DATABASE_URL is not set");
  }

  if (!global.__midasPrisma__) {
    console.log("[Prisma] Initializing Prisma 7 MariaDB Adapter client...");
    
    // Ensure we use native rust resolution, converting localhost to local IP to bypass potential named pipe delays
    let databaseUrl = process.env.DATABASE_URL;
    if (databaseUrl.startsWith("mysql://")) {
      databaseUrl = "mariadb://" + databaseUrl.substring(8);
    }
    
    // Use TCP stack explicitly
    if (databaseUrl.includes("@localhost")) {
      databaseUrl = databaseUrl.replace("@localhost", "@127.0.0.1");
    }

    // The adapter accepts the raw string and decodes the native URL (fixes %40 passwords)
    const adapter = new PrismaMariaDb(databaseUrl);

    global.__midasPrisma__ = new PrismaClient({
      adapter,
      log: process.env.NODE_ENV === "development" ? ["error", "warn"] : ["error"],
    });
  }

  return global.__midasPrisma__;
}

// Export a default instance for convenience
export const prisma = getPrismaClient();
