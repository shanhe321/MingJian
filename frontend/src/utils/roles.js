export function copyRoles(roles) {
  return Array.isArray(roles) ? [...roles] : []
}

export function validRoleSelection(roles) {
  return Array.isArray(roles) && roles.length > 0
}
