import { useState, useEffect } from "react";
import { api, auth, isLoggedIn } from "../../api";

export function UserBadge() {
  const [userId, setUserId] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoggedIn()) return;
    api.profile.whoami().then((data) => {
      const profile = data.profile as { user_id?: string; theme?: string } | undefined;
      if (profile?.user_id) setUserId(profile.user_id);
    }).catch(() => {
      const stored = localStorage.getItem("jwt_refresh_token");
      if (stored) setUserId("user");
    });
  }, []);

  if (!userId) return null;

  return (
    <div className="user-badge" style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
      <span style={{ opacity: 0.6 }}>{userId}</span>
      <button className="btn btn-ghost" style={{ fontSize: 11, padding: "2px 8px" }} onClick={() => { auth.logout(); window.location.reload(); }}>
        Sign out
      </button>
    </div>
  );
}
