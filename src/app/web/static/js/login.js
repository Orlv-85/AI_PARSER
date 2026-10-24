      const form = document.getElementById("login-form");
      const errorNode = document.getElementById("error");
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        errorNode.textContent = "";
        const payload = {
          username: document.getElementById("username").value,
          password: document.getElementById("password").value
        };
        const response = await fetch("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        if (response.ok) {
          window.location.assign("/admin");
          return;
        }
        errorNode.textContent = "Invalid username or password";
      });
