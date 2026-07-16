output "app_ids" {
  description = "Map of app label to Okta app ID."
  value       = { for label, app in okta_app_bookmark.this : label => app.id }
}
