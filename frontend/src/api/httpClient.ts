import axios from "axios"


export const httpClient = axios.create({

  baseURL: "/api",

  timeout: 15000,

  headers: {
    "Content-Type": "application/json"
  }

})