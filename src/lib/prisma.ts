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
    // Parse the mysql:// URI to support passwords with @ characters or empty passwords
    const match = process.env.DATABASE_URL.match(
      /mysql:\/\/(.+?):(.*)@([^@:]+):(\d+)\/(.+)/
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
      };
    } else {
      config = process.env.DATABASE_URL;
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
