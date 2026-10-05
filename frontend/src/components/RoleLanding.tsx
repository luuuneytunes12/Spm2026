import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { useAuth } from '../auth/useAuth'
import { useNotifications } from '../notifications/useNotifications'
import { ROLE_LANDING } from '../lib/roleLanding'
import type { LandingTile } from '../lib/roleLanding'
import { ROLE_LABELS } from '../lib/roles'
import type { Role } from '../lib/roles'
import { Icon } from './Icon'

/** The number on a tile. Loads on its own and says nothing if it fails --
 *  a missing count must never get in the way of the link beside it. */
function TileCount({ tile }: { tile: LandingTile }) {
  const { unreadCount } = useNotifications()
  const [loaded, setLoaded] = useState<number | null>(null)
  const loader = tile.count

  useEffect(() => {
    if (!loader) return
    let cancelled = false
    loader()
      .then((n) => {
        if (!cancelled) setLoaded(n)
      })
      .catch(() => {
        // Intentionally silent: see above.
      })
    return () => {
      cancelled = true
    }
  }, [loader])

  const value = tile.unreadNotifications ? unreadCount : loaded
  if (value === null || value === 0) return null
  return (
    <span className="tile-count" aria-label={`${value} ${tile.unreadNotifications ? 'unread' : 'items'}`}>
      {value}
    </span>
  )
}

/** The page a signed-in user lands on: a welcome, then a tile for each place
 *  their role can go. `children` is for a role's own live panel (the
 *  Coordinator's availability), shown between the two. */
export function RoleLanding({ role, children }: { role: Role; children?: ReactNode }) {
  const { user } = useAuth()
  const config = ROLE_LANDING[role]
  const firstName = user?.name?.split(/\s+/)[0]

  return (
    <div className="landing">
      <section className="landing-hero">
        <span className="badge badge-accent">{ROLE_LABELS[role]}</span>
        <h1>{firstName ? `Welcome back, ${firstName}` : 'Welcome back'}</h1>
        <p>{config.tagline}</p>
      </section>

      {children}

      <section aria-labelledby="landing-tiles-heading">
        <h2 id="landing-tiles-heading" className="landing-heading">
          Quick access
        </h2>
        <ul className="tile-grid">
          {config.tiles.map((tile) => (
            <li key={tile.title}>
              <Link to={tile.to} className="tile">
                <span className="tile-icon">
                  <Icon name={tile.icon} size={22} />
                </span>
                <span className="tile-body">
                  <span className="tile-title">
                    {tile.title}
                    <TileCount tile={tile} />
                  </span>
                  <span className="tile-desc">{tile.description}</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
