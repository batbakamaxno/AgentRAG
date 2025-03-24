import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

public class RegistrationTest {
    private UserRegistrationPage registrationPage;

    @BeforeEach
    public void setUp() {
        // Initialize the registration page
        this.registrationPage = new UserRegistrationPage();
    }

    @Test
    public void testSuccessfulRegistration() {
        // Fill in the name and email fields
        String name = "John Doe";
        String email = "john.doe@example.com";

        // Click the "Register" button
        registrationPage.fillNameField(name);
        registrationPage.fillEmailField(email);
        registrationPage.clickRegisterButton();

        // Verify the successful registration message
        assertEquals("Регистрация прошла успешно!", registrationPage.getSuccessMessage());
    }
}