import math
import logging

logger = logging.getLogger("OptionAnalytics")

def norm_cdf(x):
    """Cumulative distribution function for the standard normal distribution"""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))

def norm_pdf(x):
    """Probability density function for the standard normal distribution"""
    return (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * x**2)

def calculate_black_scholes(S, K, T, r, sigma, option_type='ce'):
    """
    Calculate Option Price using Black-Scholes Model.
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0

    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    if option_type.lower() in ['ce', 'call']:
        price = S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
    else:
        price = K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)

    return price

def calculate_greeks(S, K, T, r, sigma, option_type='ce'):
    """
    Calculate Greeks using Black-Scholes Model.
    Returns Vega scaled for 1% change in IV.
    """
    try:
        # Handle edge cases
        if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
            return {
                "delta": 0, "gamma": 0, "theta": 0, "vega": 0, "rho": 0
            }

        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        pdf_d1 = norm_pdf(d1)
        cdf_d1 = norm_cdf(d1)
        cdf_d2 = norm_cdf(d2)
        cdf_neg_d1 = norm_cdf(-d1)
        cdf_neg_d2 = norm_cdf(-d2)

        if option_type.lower() in ['ce', 'call']:
            delta = cdf_d1
            theta = (- (S * pdf_d1 * sigma) / (2 * math.sqrt(T)) - r * K * math.exp(-r * T) * cdf_d2) / 365.0
            rho = K * T * math.exp(-r * T) * cdf_d2
        else:
            delta = -cdf_neg_d1
            theta = (- (S * pdf_d1 * sigma) / (2 * math.sqrt(T)) + r * K * math.exp(-r * T) * cdf_neg_d2) / 365.0
            rho = -K * T * math.exp(-r * T) * cdf_neg_d2

        gamma = pdf_d1 / (S * sigma * math.sqrt(T))
        vega = S * math.sqrt(T) * pdf_d1 / 100.0 # 1% IV change

        return {
            "delta": round(delta, 4),
            "gamma": round(gamma, 6),
            "theta": round(theta, 4),
            "vega": round(vega, 4),
            "rho": round(rho, 4)
        }
    except Exception as e:
        logger.error(f"Error calculating greeks: {e}")
        return {"delta": 0, "gamma": 0, "theta": 0, "vega": 0, "rho": 0}

def calculate_iv(price, S, K, T, r, option_type='ce', tol=1e-5, max_iter=100):
    """
    Calculate Implied Volatility using Newton-Raphson method.
    """
    if price <= 0: return 0.0

    sigma = 0.5 # Initial guess
    for i in range(max_iter):
        greeks = calculate_greeks(S, K, T, r, sigma, option_type)
        theo_price = calculate_black_scholes(S, K, T, r, sigma, option_type)

        diff = theo_price - price

        if abs(diff) < tol:
            return round(sigma, 4)

        vega = greeks['vega'] * 100 # Scale to unit Vega
        if abs(vega) < 1e-8:
            break

        sigma = sigma - diff / vega

        # Clamp sigma to reasonable bounds to prevent divergence
        if sigma <= 0: sigma = 0.001
        if sigma > 5.0: sigma = 5.0

    return 0.0 # Failed to converge

def calculate_max_pain(chain_data):
    """
    Calculate Max Pain Strike.
    chain_data: List of dicts with 'strike', 'ce_oi', 'pe_oi'
    """
    try:
        strikes = []
        for item in chain_data:
            if 'strike' in item:
                 strikes.append(item['strike'])

        strikes = sorted(list(set(strikes)))
        if not strikes: return None

        total_loss = []
        for strike_price in strikes: # Expiry price
            loss = 0
            for item in chain_data:
                k = item.get('strike')
                if not k: continue

                ce_oi = item.get('ce_oi', 0)
                pe_oi = item.get('pe_oi', 0)

                # Handling nested structure if present (though logic below assumes flat)
                if 'ce' in item and isinstance(item['ce'], dict):
                     ce_oi = item['ce'].get('oi', 0)
                if 'pe' in item and isinstance(item['pe'], dict):
                     pe_oi = item['pe'].get('oi', 0)

                # Call writers lose if expiry (strike_price) > k (strike of option)
                if strike_price > k:
                    loss += (strike_price - k) * ce_oi

                # Put writers lose if expiry (strike_price) < k
                if strike_price < k:
                    loss += (k - strike_price) * pe_oi

            total_loss.append(loss)

        if not total_loss: return None

        min_loss_idx = total_loss.index(min(total_loss))
        return strikes[min_loss_idx]
    except Exception as e:
        logger.error(f"Error calculating max pain: {e}")
        return None

def calculate_pcr(chain_data):
    """
    Calculate Put-Call Ratio based on Open Interest.
    """
    try:
        total_ce_oi = 0
        total_pe_oi = 0

        for item in chain_data:
            # Handle flattened or nested structure
            if 'ce_oi' in item:
                total_ce_oi += item.get('ce_oi', 0)
                total_pe_oi += item.get('pe_oi', 0)
            else:
                total_ce_oi += item.get('ce', {}).get('oi', 0)
                total_pe_oi += item.get('pe', {}).get('oi', 0)

        if total_ce_oi == 0:
            return 0
        return round(total_pe_oi / total_ce_oi, 2)
    except Exception as e:
        logger.error(f"Error calculating PCR: {e}")
        return 0
