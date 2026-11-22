import { Link } from "react-router";

export function Logo() {
  return <Link className="logo" to="/" data-testid="header-home"><svg viewBox="-50 -50 100 100" aria-hidden="true"><circle className="logo-ring" r="44" fill="none" stroke="currentColor" strokeWidth="6" /><circle className="logo-beat" r="8" fill="var(--color-saffron)" /></svg><span>Naadi <b aria-hidden="true">नाड़ी</b></span></Link>;
}
