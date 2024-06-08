from warriors.rating import compute_omega_matrix


for k in [0, 1, 2, 3]:
    omega = compute_omega_matrix(k)
    print(omega)
