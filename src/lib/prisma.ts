import { PrismaClient } from "@prisma/client";
import { PrismaMariaDb } from "@prisma/adapter-mariadb";
import * as mariadb from "mariadb";

declare global {
  var __midasPrisma__: unknown;
}

type PrismaLike = {
  $queryRaw: (...args: unknown[]) => Promise<unknown>;
  $queryRawUnsafe: (query: string, ...values: unknown[]) => Promise<unknown>;
  $executeRaw: (...args: unknown[]) => Promise<unknown>;
  $executeRawUnsafe: (query: string, ...values: unknown[]) => Promise<unknown>;
};

export function getPrismaClient(): PrismaLike | null {
  if (!process.env.DATABASE_URL) {
    return null;
  }

  if (!global.__midasPrisma__) {
    console.log("[Prisma] Initializing new MariaDB adapter client...");
    // Ensure we use the mariadb:// protocol and 127.0.0.1 for local connections
    let rawUrl = process.env.DATABASE_URL;
    if (rawUrl.startsWith("mysql://")) {
      rawUrl = "mariadb://" + rawUrl.substring(8);
    }
    rawUrl = rawUrl.replace("@localhost", "@127.0.0.1");

    const match = rawUrl.match(
      /mariadb:\/\/(.+?):(.*)@([^@:]+):(\d+)\/(.+)/
    );
    
    let config: any;
    if (match) {
      config = {
        user: match[1],
        password: match[2],
        host: match[3],
        port: parseInt(match[4], 10),
        database: match[5],
        connectionLimit: 10,
        acquireTimeout: 30000, // 30 seconds
        connectTimeout: 10000, // 10 seconds
      };
    } else {
      config = rawUrl;
    }
    
    // The adapter expects PoolConfig, not an initialized Pool.
    const adapter = new PrismaMariaDb(config);

    global.__midasPrisma__ = new PrismaClient({
      adapter,
      log: process.env.NODE_ENV === "development" ? ["error", "warn"] : ["error"],
    });
  }

  return global.__midasPrisma__ as PrismaLike;
}
