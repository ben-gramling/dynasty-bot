import { Db, MongoClient } from "mongodb";
// Ensure the AWS credential provider is included in the standalone build trace.
// The MongoDB driver loads it dynamically for MONGODB-AWS auth.
import "@aws-sdk/credential-providers";

declare global {
  // eslint-disable-next-line no-var
  var _mongoClientPromise: Promise<MongoClient> | undefined;
}

let _clientPromise: Promise<MongoClient> | undefined;

/**
 * Connect without ever caching a rejection: if connect() fails (transient
 * Atlas outage, DNS blip), `clearCache` empties the cache slot so the next
 * request builds a fresh client instead of replaying the cached rejection
 * forever. The catch is attached at creation, so it runs before any awaiting
 * caller observes the rejection — a retry always sees an empty slot.
 */
function connectFresh(uri: string, clearCache: () => void): Promise<MongoClient> {
  const promise = new MongoClient(uri).connect();
  promise.catch(clearCache);
  return promise;
}

function getClientPromise(): Promise<MongoClient> {
  const uri = process.env.MONGODB_URI;
  if (!uri) throw new Error("MONGODB_URI environment variable is not set");

  if (process.env.NODE_ENV === "development") {
    // Cache on globalThis so hot reloads reuse one client.
    if (!global._mongoClientPromise) {
      const promise = connectFresh(uri, () => {
        // Only clear our own promise — never a newer, healthy one.
        if (global._mongoClientPromise === promise) {
          global._mongoClientPromise = undefined;
        }
      });
      global._mongoClientPromise = promise;
    }
    return global._mongoClientPromise;
  }

  if (!_clientPromise) {
    const promise = connectFresh(uri, () => {
      if (_clientPromise === promise) _clientPromise = undefined;
    });
    _clientPromise = promise;
  }
  return _clientPromise;
}

/** The dynasty-bot database, selected by name — never via the URI path. */
export async function getDb(): Promise<Db> {
  const client = await getClientPromise();
  return client.db(process.env.MONGODB_DB ?? "dynasty-bot");
}

export default getClientPromise;
