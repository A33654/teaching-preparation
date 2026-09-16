import { defineStore } from "pinia"
import { ref } from "vue"
import { authApi, TOKEN_KEY } from "@/api"
import type { UserPublic } from "@/types"

export const useAuthStore = defineStore("auth", () => {
  const user = ref<UserPublic | null>(null)
  const loading = ref(false)

  async function fetchMe() {
    try {
      const resp = await authApi.me()
      user.value = resp.data
    } catch {
      user.value = null
    }
  }

  async function login(username: string, password: string) {
    const resp = await authApi.login(username, password)
    localStorage.setItem(TOKEN_KEY, resp.data.access_token)
    await fetchMe()
  }

  async function register(data: { email: string; password: string; full_name?: string }) {
    await authApi.signup(data)
  }

  function logout() {
    localStorage.removeItem(TOKEN_KEY)
    user.value = null
  }

  const isLoggedIn = () => !!localStorage.getItem(TOKEN_KEY)

  return { user, loading, fetchMe, login, register, logout, isLoggedIn }
})
