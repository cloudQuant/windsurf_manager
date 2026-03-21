from app.database import SessionLocal
from app import crud

ACCOUNTS = [
    ("Account-01", "c1nh34snml@zfkisry.shop", "=sTf80TmTVCW.}vM"),
    ("Account-02", "aprz3hm8pq@zfkisry.shop", "V*3R)xAsbn:k2B6C"),
    ("Account-03", "94u4nwyxll@zfkisry.shop", "!H%C*h3%.T5e#glZ"),
    ("Account-04", "71dwtfvxtt@zfkisry.shop", "xV@&UTYv*27&vmOJ"),
    ("Account-05", "8fsjhv9if8@rvjyzpo.shop", "(Ug@4?85-OIo:aFl"),
    ("Account-06", "kd0tupna7u@rvjyzpo.shop", "0)v)d-1uOywNxQpM"),
    ("Account-07", "nvt9om8l73@rvjyzpo.shop", "LnFOQzpn81_t+$3o"),
    ("Account-08", "giqqgcz3tr@rvjyzpo.shop", "8Z^.PwBz[Rn7D1Hp"),
    ("Account-09", "g6e0nou7rb@rvjyzpo.shop", "%2M18z0..QZAv^w{"),
    ("Account-10", "6f5aktnkka@rvjyzpo.shop", "M?010za3HN..d*qY"),
]


def main():
    db = SessionLocal()
    try:
        for name, email, password in ACCOUNTS:
            account = crud.get_account_by_email(db, email)
            if not account:
                print(f"MISSING {email}")
                continue
            crud.update_account(
                db,
                account.id,
                name=account.name or name,
                email=account.email,
                password=password,
                api_key=account.api_key,
            )
            print(f"UPDATED {email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
