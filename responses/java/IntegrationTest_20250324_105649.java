import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

public class IntegrationTest {
    private UserRegistrationPage registrationPage;
    
    @BeforeEach
    public void setUp() {
        // Initialize the registration page
        this.registrationPage = new UserRegistrationPage();
    }
    
    @Test
    public void testSuccessfulIntegration() {
        // Create a test order in System A
        Order order = new Order();
        order.setOrderId("TEST-123");
        order.setAmount(1500.0);
        order.setCustomerEmail("test@example.com");
        order.setItems(Arrays.asList("Item1", "Item2"));
        
        // Send the order to System B for integration
        registrationPage.sendOrder(order);
        
        // Verify that the order was successfully integrated in System B
        assertEquals(OrderStatus.SUCCESS, registrationPage.getOrderStatus());
        assertEquals("TEST-123", registrationPage.getOrderId());
        assertEquals(1500.0, registrationPage.getAmount());
        assertEquals("test@example.com", registrationPage.getCustomerEmail());
        assertEquals("Item1, Item2", registrationPage.getItems());
    }
    
    @Test
    public void testInvalidIntegration() {
        // Create a test order in System A with invalid data
        Order order = new Order();
        order.setOrderId("INVALID-ORDER-ID");
        order.setAmount(0.0);
        order.setCustomerEmail("invalid-email@example.com");
        order.setItems(Collections.emptyList());
        
        // Attempt to send the order to System B for integration
        registrationPage.sendOrder(order);
        
        // Verify that the order was not successfully integrated in System B
        assertEquals(OrderStatus.INVALID_ORDER_ID, registrationPage.getOrderStatus());
        assertEquals("INVALID-ORDER-ID", registrationPage.getOrderId());
        assertEquals(0.0, registrationPage.getAmount());
        assertEquals("invalid-email@example.com", registrationPage.getCustomerEmail());
        assertEquals(Collections.emptyList(), registrationPage.getItems());
    }
}